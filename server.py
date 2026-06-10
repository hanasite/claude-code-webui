#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 对话管理 WebUI — 后端 API 服务"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from flask import Flask, jsonify, request, send_from_directory, abort

app = Flask(__name__, static_folder=None)

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_FILE = CLAUDE_DIR / "history.jsonl"
LABELS_FILE = Path(__file__).parent / "labels.json"
SKILLS_DIRS = [
    CLAUDE_DIR / "skills",
    Path.home() / ".openclaw" / "workspace" / "skills",
]

SKILLHUB_SEARCH_URL = "https://api.skillhub.cn/api/v1/search"
SKILLHUB_DOWNLOAD_URL = "https://api.skillhub.cn/api/v1/download"

# MCP Sessions Web 服务地址（claude-sessions-mcp 内置 Web UI）
MCP_WEB_URL = "http://localhost:5173"


# ── helpers ──────────────────────────────────────────────────

def _safe_path(path_str: str, base: Path) -> Path:
    """防止路径穿越攻击"""
    resolved = (base / unquote(path_str)).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError("path traversal")
    return resolved


def _read_jsonl(path: Path, limit: int = 0) -> list[dict]:
    """读取 JSONL 文件，返回 dict 列表。limit=0 表示全部"""
    items = []
    if not path.exists():
        return items
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(items) >= limit:
                break
    return items


def _count_jsonl(path: Path) -> int:
    """快速统计 JSONL 行数"""
    if not path.exists():
        return 0
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _ts_to_str(ts) -> str:
    """毫秒时间戳 → ISO 字符串"""
    try:
        ts_int = int(ts)
        if ts_int > 1e12:
            ts_int = ts_int // 1000
        return datetime.fromtimestamp(ts_int, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def _project_key_to_dir(key: str) -> str:
    """C--Users-kakun -> C:\\Users\\kakun
    优先从 session 文件提取真实 cwd（同 @claude-sessions/core 的策略），
    降级为字符串替换 + 文件系统验证。
    """
    # 策略 1：从 session 文件读取真实 cwd（最准确）
    real = _get_cwd_from_sessions(key)
    if real:
        return real

    # 策略 2：字符串替换 + 文件系统存在性验证
    path = key.replace("--", ":\\").replace("-", "\\")
    if os.path.exists(path):
        return path
    return _fix_path_segments(path.split("\\"))


def _get_cwd_from_sessions(project_key: str) -> str | None:
    """从项目目录的 session 文件中提取真实 cwd（仿 @claude-sessions/core，带缓存）"""
    if project_key in _cwd_cache:
        return _cwd_cache[project_key]

    project_dir = PROJECTS_DIR / project_key
    if not project_dir.exists():
        return None
    try:
        for f in sorted(project_dir.glob("*.jsonl")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    for _ in range(5):
                        line = fh.readline()
                        if not line:
                            break
                        try:
                            d = json.loads(line.strip())
                            if "cwd" in d and d["cwd"]:
                                _cwd_cache[project_key] = str(d["cwd"])
                                return _cwd_cache[project_key]
                        except json.JSONDecodeError:
                            continue
            except Exception:
                continue
    except Exception:
        pass
    _cwd_cache[project_key] = ""  # 空字符串表示已查过但没找到
    return None


def _fix_path_segments(parts: list) -> str:
    """递归修正路径：合并相邻段直到找到存在的目录"""
    current = parts[0]
    if not os.path.exists(current):
        return "\\".join(parts)

    i = 1
    while i < len(parts):
        parent = current
        found = None
        # 尝试从 i 开始合并尽可能多的段
        for j in range(len(parts) - i, -1, -1):
            chunk = parts[i:i+j+1]
            for sep in ["_", " ", "-", ""]:
                cand = sep.join(chunk)
                full = parent + "\\" + cand
                if os.path.exists(full):
                    found = (full, i + j + 1)
                    break
            if found:
                break
        if found:
            current, i = found
        else:
            current += "\\" + parts[i]
            i += 1
    return current


def _try_match(parent: str, parts: list, start: int):
    """尝试从 start 位置合并若干段，找到存在于 parent 下的目录。返回 (full_path, new_i) 或 None"""
    for j in range(len(parts) - start, 0, -1):
        merged = parts[start:start+j]
        for sep in ["_", " ", "-", ""]:
            cand = sep.join(merged)
            full = parent + "\\" + cand if not parent.endswith("\\") else parent + cand
            if os.path.exists(full):
                return (full, start + j)
    return None


def _get_sessions(project_path: Path, project_key: str = "", sort_by: str = "time_desc") -> list[dict]:
    """获取项目下所有会话"""
    work_dir = _project_key_to_dir(project_key) if project_key else ""
    sessions = []
    if not project_path.exists():
        return sessions
    for f in sorted(project_path.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not f.name.endswith(".jsonl"):
            continue
        sid = f.stem
        stat = f.stat()
        msg_count = _count_jsonl(f)

        # 读取第一条和最后一条消息获取摘要信息
        messages = _read_jsonl(f, limit=2)
        first_msg = messages[0] if messages else {}
        title = ""
        created_at = ""
        for m in messages:
            if m.get("type") == "user":
                title = str(m.get("message", {}).get("content", ""))[:100]
                break
        # 从文件名或第一条消息推断时间
        created_at = _ts_to_str(first_msg.get("timestamp", 0)) if first_msg.get("timestamp") else _ts_to_str(int(stat.st_mtime))

        # 读取最后一行获取最后时间
        last_time = ""
        last_ts = 0
        with open(f, "rb") as fh:
            fh.seek(max(0, stat.st_size - 500))
            tail = fh.read().decode("utf-8", errors="ignore")
            lines = tail.strip().split("\n")
            if lines:
                try:
                    last = json.loads(lines[-1])
                    last_ts = int(last.get("timestamp", 0))
                    last_time = _ts_to_str(last_ts)
                except Exception:
                    pass

        sessions.append({
            "id": sid,
            "message_count": msg_count,
            "size_bytes": stat.st_size,
            "size_display": _format_size(stat.st_size),
            "title": title or f"会话 {sid[:8]}",
            "created_at": created_at,
            "last_message_at": last_time or created_at,
            "last_ts": last_ts,
            "resume_command": f'cd /d "{work_dir}" && claude --resume {sid}' if work_dir else f"claude --resume {sid}",
        })

    # 排序
    sort_keys = {
        "time_desc": lambda s: s["last_ts"],
        "time_asc": lambda s: -s["last_ts"],
        "size": lambda s: s["size_bytes"],
        "messages": lambda s: s["message_count"],
    }
    key_fn = sort_keys.get(sort_by, sort_keys["time_desc"])
    sessions.sort(key=key_fn, reverse=True)
    return sessions


def _format_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _load_labels() -> dict:
    """加载自定义标签"""
    if LABELS_FILE.exists():
        try:
            return json.loads(LABELS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_labels(labels: dict):
    """保存自定义标签"""
    LABELS_FILE.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")


# MCP 状态（启动时检测一次，后续用缓存）和 cwd 缓存
_mcp_online = False
_cwd_cache = {}  # project_key -> real_path


def _check_mcp():
    """启动时检测 MCP 是否可用"""
    global _mcp_online
    try:
        req = urllib.request.Request(f"{MCP_WEB_URL}/api/projects")
        urllib.request.urlopen(req, timeout=1)
        _mcp_online = True
    except Exception:
        _mcp_online = False


def _mcp_api(path: str) -> dict | list | None:
    """调用 MCP Sessions Web API"""
    try:
        req = urllib.request.Request(f"{MCP_WEB_URL}{path}")
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read())
    except Exception:
        return None


def _get_sessions_fallback(project_path: Path, project_key: str = "", sort_by: str = "time_desc") -> list[dict]:
    """MCP 不可用时的降级方案：直接读取本地 JSONL 文件"""
    sort_keys = {
        "time_desc": lambda s: s["last_ts"],
        "time_asc": lambda s: -s["last_ts"],
        "size": lambda s: s["size_bytes"],
        "messages": lambda s: s["message_count"],
    }
    sessions = []
    if not project_path.exists():
        return sessions

    for f in sorted(project_path.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        sid = f.stem
        stat = f.stat()
        msg_count = _count_jsonl(f)
        title = sid[:8]
        created_at = _ts_to_str(int(stat.st_mtime))
        last_ts = int(stat.st_mtime)
        last_time = _ts_to_str(last_ts)

        for m in _read_jsonl(f, limit=3):
            if m.get("type") == "user":
                title = str(m.get("message", {}).get("content", ""))[:100]
                break

        work_dir = _project_key_to_dir(project_key) if project_key else ""
        sessions.append({
            "id": sid,
            "message_count": msg_count,
            "size_bytes": stat.st_size,
            "size_display": _format_size(stat.st_size),
            "title": title or f"会话 {sid[:8]}",
            "created_at": created_at,
            "last_message_at": last_time,
            "last_ts": last_ts,
            "resume_command": f'cd /d "{work_dir}" && claude --resume {sid}' if work_dir else f"claude --resume {sid}",
        })

    sessions.sort(key=sort_keys.get(sort_by, sort_keys["time_desc"]), reverse=True)
    return sessions


# ── static files ─────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.template_folder, "index.html")


# ── API ──────────────────────────────────────────────────────

@app.route("/api/projects")
def api_projects():
    """列出所有项目（优先 MCP，降级本地文件）"""
    projects = []
    mcp_data = _mcp_api("/api/projects") if _mcp_online else None

    if mcp_data:
        # MCP 模式：路径正确
        for p in mcp_data:
            key = p.get("name", "")
            display = p.get("displayName", key)
            if display == "~":
                display = str(Path.home())
            elif display.startswith("~/"):
                display = str(Path.home() / display[2:])
            display = display.replace("/", "\\")

            proj_dir = PROJECTS_DIR / key
            memory_files = [f.name for f in (proj_dir / "memory").glob("*.md")] if (proj_dir / "memory").exists() else []

            projects.append({
                "key": key,
                "name": display,
                "session_count": p.get("sessionCount", 0),
                "total_size": "-",
                "memory_files": memory_files,
            })
    else:
        # Fallback：本地文件（不读会话详情，仅文件名扫描）
        if PROJECTS_DIR.exists():
            for d in sorted(PROJECTS_DIR.iterdir()):
                if not d.is_dir() or d.name.startswith("."):
                    continue
                jsons = list(d.glob("*.jsonl"))
                memory_files = [f.name for f in (d / "memory").glob("*.md")] if (d / "memory").exists() else []
                projects.append({
                    "key": d.name,
                    "name": _project_key_to_dir(d.name),
                    "session_count": len(jsons),
                    "total_size": _format_size(sum(f.stat().st_size for f in jsons)),
                    "memory_files": memory_files,
                })

    return jsonify(projects)


@app.route("/api/sessions/<path:project_key>")
def api_sessions(project_key: str):
    """列出项目下所有会话（优先 MCP，降级本地文件）+ 自定义标签"""
    labels = _load_labels()
    try:
        proj_path = _safe_path(project_key, PROJECTS_DIR)
    except ValueError:
        abort(400)

    sort_by = request.args.get("sort", "time_desc")

    if _mcp_online:
        mcp_projects = _mcp_api("/api/projects") or []
        work_dir = ""
        for p in mcp_projects:
            if p.get("name") == project_key:
                work_dir = p.get("displayName", "").replace("/", "\\")
                if work_dir == "~":
                    work_dir = str(Path.home())
                break

        sessions_raw = _mcp_api(f"/api/sessions?project={project_key}") or []
        sessions = []
        for s in sessions_raw:
            sid = s.get("id", "")
            sessions.append({
                "id": sid,
                "message_count": int(s.get("messageCount", 0)),
                "size_bytes": 0,
                "size_display": "-",
                "title": s.get("title", f"会话 {sid[:8]}")[:100],
                "created_at": s.get("createdAt", ""),
                "last_message_at": s.get("updatedAt", ""),
                "last_ts": 0,
                "label": labels.get(sid, ""),
                "resume_command": f'cd /d "{work_dir}" && claude --resume {sid}' if work_dir else f"claude --resume {sid}",
            })

        if sort_by == "time_asc":
            sessions.reverse()
        elif sort_by == "messages":
            sessions.sort(key=lambda s: s["message_count"], reverse=True)
    else:
        sessions = _get_sessions_fallback(proj_path, project_key=project_key, sort_by=sort_by)
        for s in sessions:
            if s["id"] in labels:
                s["label"] = labels[s["id"]]

    return jsonify(sessions)


@app.route("/api/session/<path:project_key>/<session_id>")
def api_session(project_key: str, session_id: str):
    """获取会话消息，支持分页"""
    try:
        proj_path = _safe_path(project_key, PROJECTS_DIR)
    except ValueError:
        abort(400)

    # 安全检查 session_id 不含路径分隔符
    session_id = os.path.basename(session_id)
    session_file = proj_path / f"{session_id}.jsonl"
    if not session_file.exists():
        abort(404)

    page = max(1, request.args.get("page", 1, type=int))
    per = min(500, max(10, request.args.get("per", 100, type=int)))

    all_msgs = _read_jsonl(session_file)
    total = len(all_msgs)

    # 分页
    start = (page - 1) * per
    end = start + per
    page_msgs = all_msgs[start:end]

    # 简化消息格式供前端渲染
    messages = []
    for m in page_msgs:
        msg_type = m.get("type", "unknown")
        role = "system"
        content = ""

        if msg_type == "user":
            role = "user"
            content = m.get("message", {}).get("content", "") if isinstance(m.get("message"), dict) else str(m.get("message", ""))
        elif msg_type == "assistant":
            role = "assistant"
            content = m.get("message", {}).get("content", "") if isinstance(m.get("message"), dict) else str(m.get("message", ""))
            if isinstance(content, list):
                # content blocks
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            parts.append(f'[Tool: {block.get("name","")}]')
                        elif block.get("type") == "tool_result":
                            parts.append(f'[Result]')
                    else:
                        parts.append(str(block)[:200])
                content = "\n".join(parts)
        elif msg_type in ("tool_use", "tool_result"):
            role = "tool"
            content = json.dumps(m, ensure_ascii=False, default=str)[:5000]
        elif msg_type in ("mode", "attribution-snapshot", "model"):
            role = "meta"
            content = str(m)[:200]
        else:
            role = "meta"
            content = str(m)[:500]

        messages.append({
            "type": msg_type,
            "role": role,
            "content": str(content),
            "timestamp": _ts_to_str(m.get("timestamp", 0)) if m.get("timestamp") else "",
            "raw": m if msg_type in ("tool_use", "tool_result") else None,
        })

    return jsonify({
        "session_id": session_id,
        "total": total,
        "page": page,
        "per": per,
        "pages": max(1, (total + per - 1) // per),
        "messages": messages,
    })


@app.route("/api/session/<path:project_key>/<session_id>", methods=["DELETE"])
def api_delete_session(project_key: str, session_id: str):
    """删除一个会话"""
    try:
        proj_path = _safe_path(project_key, PROJECTS_DIR)
    except ValueError:
        abort(400)

    session_id = os.path.basename(session_id)
    session_file = proj_path / f"{session_id}.jsonl"
    session_dir = proj_path / session_id

    deleted = []
    if session_file.exists():
        session_file.unlink()
        deleted.append(str(session_file))
    if session_dir.exists():
        import shutil
        shutil.rmtree(session_dir)
        deleted.append(str(session_dir))

    return jsonify({"deleted": deleted, "ok": True})


@app.route("/api/export/<path:project_key>/<session_id>")
def api_export(project_key: str, session_id: str):
    """导出会话为 Markdown"""
    try:
        proj_path = _safe_path(project_key, PROJECTS_DIR)
    except ValueError:
        abort(400)

    session_id = os.path.basename(session_id)
    session_file = proj_path / f"{session_id}.jsonl"
    if not session_file.exists():
        abort(404)

    all_msgs = _read_jsonl(session_file)
    md_lines = [f"# 会话 {session_id[:8]}\n", f"项目: {project_key}\n", f"消息数: {len(all_msgs)}\n", "\n---\n\n"]

    for m in all_msgs:
        t = m.get("type", "")
        ts = _ts_to_str(m.get("timestamp", 0))
        if t == "user":
            content = m.get("message", {}).get("content", "") if isinstance(m.get("message"), dict) else str(m.get("message", ""))
            md_lines.append(f"### 🙋 用户 ({ts})\n\n{content}\n\n")
        elif t == "assistant":
            content = m.get("message", {}).get("content", "") if isinstance(m.get("message"), dict) else str(m.get("message", ""))
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        md_lines.append(f"### 🤖 Claude ({ts})\n\n{block.get('text', '')}\n\n")
            else:
                md_lines.append(f"### 🤖 Claude ({ts})\n\n{str(content)}\n\n")
        elif t == "mode":
            md_lines.append(f"> 模式: {m.get('mode', '')}\n\n")

    md = "".join(md_lines)
    return md, 200, {
        "Content-Type": "text/markdown; charset=utf-8",
        "Content-Disposition": f"attachment; filename=session-{session_id[:8]}.md",
    }


@app.route("/api/search")
def api_search():
    """跨项目搜索会话内容"""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": [], "query": q})

    results = []
    q_lower = q.lower()

    if not PROJECTS_DIR.exists():
        return jsonify({"results": [], "query": q})

    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        for f in proj_dir.glob("*.jsonl"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    matches = []
                    for line_num, line in enumerate(fh):
                        line = line.strip()
                        if not line:
                            continue
                        if q_lower in line.lower():
                            try:
                                m = json.loads(line)
                                t = m.get("type", "")
                                if t in ("user", "assistant"):
                                    content = m.get("message", {}).get("content", "") if isinstance(m.get("message"), dict) else str(m.get("message", ""))
                                    if isinstance(content, list):
                                        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                                    matches.append({
                                        "line": line_num + 1,
                                        "type": t,
                                        "preview": str(content)[:200],
                                        "timestamp": _ts_to_str(m.get("timestamp", 0)) if m.get("timestamp") else "",
                                    })
                            except Exception:
                                pass
                            if len(matches) >= 20:
                                break
                    if matches:
                        results.append({
                            "project": proj_dir.name,
                            "session_id": f.stem,
                            "matches": matches,
                        })
            except Exception:
                continue
            if len(results) >= 10:
                break
        if len(results) >= 10:
            break

    return jsonify({"results": results, "query": q})


@app.route("/api/memory/<path:project_key>")
def api_memory(project_key: str):
    """获取项目记忆"""
    try:
        proj_path = _safe_path(project_key, PROJECTS_DIR)
    except ValueError:
        abort(400)

    memory_dir = proj_path / "memory"
    if not memory_dir.exists():
        return jsonify([])

    files = []
    for f in sorted(memory_dir.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            content = "(无法读取)"
        files.append({
            "name": f.name,
            "size": _format_size(f.stat().st_size),
            "content": content,
            "modified": _ts_to_str(int(f.stat().st_mtime)),
        })
    return jsonify(files)


# ── Labels API ────────────────────────────────────────────────

@app.route("/api/labels", methods=["GET"])
def api_labels_get():
    """获取所有自定义标签"""
    return jsonify(_load_labels())


@app.route("/api/labels/<session_id>", methods=["PUT"])
def api_labels_put(session_id: str):
    """设置会话标签 {"label": "name"}"""
    data = request.get_json(silent=True)
    if not data or "label" not in data:
        abort(400)
    labels = _load_labels()
    labels[session_id] = data["label"].strip()[:100]
    _save_labels(labels)
    return jsonify({"ok": True, "session_id": session_id, "label": labels[session_id]})


@app.route("/api/labels/<session_id>", methods=["DELETE"])
def api_labels_delete(session_id: str):
    """删除会话标签"""
    labels = _load_labels()
    labels.pop(session_id, None)
    _save_labels(labels)
    return jsonify({"ok": True})


# ── Skills API ───────────────────────────────────────────────

def _find_skill_dir(name: str) -> Path | None:
    """在所有 skills 目录中查找指定 skill"""
    name = os.path.basename(name)  # 防穿越
    for skills_dir in SKILLS_DIRS:
        skill_dir = skills_dir / name
        if skill_dir.exists() and (skill_dir / "SKILL.md").exists():
            return skill_dir
    return None


def _list_skills() -> list[dict]:
    """列出所有已安装的 skills"""
    seen = set()
    skills = []
    for skills_dir in SKILLS_DIRS:
        if not skills_dir.exists():
            continue
        for d in sorted(skills_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            skill_md = d / "SKILL.md"
            if d.name in seen or not skill_md.exists():
                continue
            seen.add(d.name)

            # 解析 SKILL.md frontmatter
            meta = {"name": d.name, "description": "", "version": ""}
            try:
                content = skill_md.read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        for line in parts[1].strip().split("\n"):
                            line = line.strip()
                            if ":" in line:
                                key, val = line.split(":", 1)
                                meta[key.strip()] = val.strip().strip('"')
            except Exception:
                pass

            # _meta.json 补充版本信息
            meta_file = d / "_meta.json"
            if meta_file.exists():
                try:
                    m = json.loads(meta_file.read_text(encoding="utf-8"))
                    meta["version"] = m.get("version", meta["version"])
                    meta["slug"] = m.get("slug", "")
                except Exception:
                    pass

            skills.append({
                "name": d.name,
                "display_name": meta.get("name", d.name),
                "description": meta.get("description", "")[:150],
                "version": meta.get("version", ""),
                "slug": meta.get("slug", d.name),
                "path": str(d),
                "source": "claude" if str(d).startswith(str(SKILLS_DIRS[0])) else "openclaw",
            })
    return skills


@app.route("/api/skills")
def api_skills():
    """列出已安装的 skills 和 skillhub 搜索结果"""
    mode = request.args.get("mode", "installed")
    if mode == "search":
        q = request.args.get("q", "").strip()
        if len(q) < 1:
            return jsonify({"results": []})
        return jsonify(_search_skillhub(q))

    return jsonify(_list_skills())


def _search_skillhub(q: str) -> dict:
    """搜索 skillhub"""
    url = f"{SKILLHUB_SEARCH_URL}?q={urllib.parse.quote(q)}"
    ctx = _create_ssl_context()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ClaudeCodeWebUI/1.0"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=10)
        data = json.loads(resp.read())
        results = []
        for r in data.get("results", [])[:20]:
            results.append({
                "slug": r.get("slug", ""),
                "name": r.get("displayName", r.get("name", "")),
                "description": r.get("description_zh", r.get("description", ""))[:200],
                "version": r.get("version", ""),
                "downloads": r.get("downloads", 0),
                "stars": r.get("stars", 0),
                "owner": r.get("owner_name", ""),
                "source": r.get("source", ""),
            })
        return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}


@app.route("/api/skills/<name>")
def api_skill_detail(name: str):
    """查看 skill 详情"""
    skill_dir = _find_skill_dir(name)
    if not skill_dir:
        abort(404)

    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    # 提取 body（跳过 frontmatter）
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else content

    files = [f.name for f in skill_dir.rglob("*") if f.is_file()]

    return jsonify({
        "name": name,
        "path": str(skill_dir),
        "content": content[:100000],
        "body": body[:80000],
        "files": files,
    })


@app.route("/api/skills/<name>", methods=["DELETE"])
def api_skill_delete(name: str):
    """卸载 skill"""
    skill_dir = _find_skill_dir(name)
    if not skill_dir:
        abort(404)

    shutil.rmtree(skill_dir)
    return jsonify({"ok": True, "deleted": str(skill_dir)})


@app.route("/api/skills/install", methods=["POST"])
def api_skill_install():
    """安装 skill（从 skillhub 下载）"""
    data = request.get_json(silent=True)
    if not data or "slug" not in data:
        abort(400)

    slug = data["slug"]
    # 目标目录：优先 ~/.claude/skills/
    target_dir = SKILLS_DIRS[0]

    # 下载
    ctx = _create_ssl_context()
    url = f"{SKILLHUB_DOWNLOAD_URL}?slug={urllib.parse.quote(slug)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ClaudeCodeWebUI/1.0"})
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        zip_data = resp.read()
    except Exception as e:
        return jsonify({"ok": False, "error": f"下载失败: {e}"}), 500

    # 解压
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "skill.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_data)

            extract_dir = os.path.join(tmpdir, "extract")
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # 找到 SKILL.md 所在目录
            skill_name = None
            for root, dirs, files in os.walk(extract_dir):
                if "SKILL.md" in files:
                    # 读取 frontmatter 获取 name
                    md_path = os.path.join(root, "SKILL.md")
                    content = Path(md_path).read_text(encoding="utf-8")
                    name = slug
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            for line in parts[1].strip().split("\n"):
                                line = line.strip()
                                if line.startswith("name:") or line.startswith("name "):
                                    name = line.split(":", 1)[1].strip().strip('"')
                                    break
                    skill_name = name or slug
                    # 复制所有文件到目标
                    dest = target_dir / skill_name
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(root, dest)
                    break

            if not skill_name:
                return jsonify({"ok": False, "error": "压缩包中未找到 SKILL.md"}), 400

        return jsonify({"ok": True, "name": skill_name, "path": str(target_dir / skill_name)})
    except zipfile.BadZipFile:
        return jsonify({"ok": False, "error": "下载的文件不是有效的 zip 压缩包"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _create_ssl_context():
    """创建不验证证书的 SSL 上下文（用于下载 skillhub 资源）"""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ── Popup ────────────────────────────────────────────────────

NOTIFY_SCRIPT = str(SKILLS_DIRS[0] / "task-notifier" / "scripts" / "notify.ps1")


@app.route("/api/resume/<path:project_key>/<session_id>", methods=["POST"])
def api_resume_session(project_key: str, session_id: str):
    """在 CMD 窗口中启动 Claude Code 会话"""
    session_id = os.path.basename(session_id)
    work_dir = ""

    if _mcp_online:
        mcp_projects = _mcp_api("/api/projects") or []
        for p in mcp_projects:
            if p.get("name") == project_key:
                work_dir = p.get("displayName", "").replace("/", "\\")
                if work_dir == "~":
                    work_dir = str(Path.home())
                break

    if not work_dir:
        work_dir = _project_key_to_dir(project_key)

    if not work_dir:
        abort(400, "无法确定项目目录")

    cli = request.args.get("cli", "claude")
    cmd_line = f'cd /d "{work_dir}" && {cli} --resume {session_id}'

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "Claude Code", "cmd", "/k", cmd_line],
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
        )
        return jsonify({"ok": True, "command": cmd_line})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/popup", methods=["POST"])
def api_popup():
    """调用本地 PowerShell 弹窗"""
    data = request.get_json(silent=True)
    if not data:
        abort(400)

    title = data.get("title", "Claude Code")
    message = data.get("message", "")
    icon = data.get("icon", "Info")

    if not os.path.exists(NOTIFY_SCRIPT):
        return jsonify({"ok": False, "error": "notify.ps1 not found"}), 500

    try:
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", NOTIFY_SCRIPT,
             "-Title", title, "-Message", message, "-Icon", icon],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── main ─────────────────────────────────────────────────────

def main():
    import webbrowser
    import sys
    import threading

    host = "127.0.0.1"
    port = 19876

    # 启动时检测 MCP 状态
    _check_mcp()

    print(f"\n== Claude Code Conversation Manager ==")
    print(f"   URL: http://{host}:{port}")
    print(f"   Data: {CLAUDE_DIR}")
    print(f"   MCP: {'connected' if _mcp_online else 'fallback mode (local files)'}")
    print(f"   Press Ctrl+C to stop\n")

    if "--no-browser" not in sys.argv:
        # 等服务器就绪后再打开浏览器，避免"拒绝连接"
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    app.template_folder = str(Path(__file__).parent / "templates")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
