# Claude Code WebUI — 对话管理与 Skills 管理器

浏览器端管理 Claude Code 对话历史、搜索会话、导出 Markdown、安装和管理 Skills。支持 Windows 原生弹窗通知和侧滑面板。

## 架构

```
┌──────────────────────────────────────────────────┐
│                    浏览器                          │
├─────────────────────┬────────────────────────────┤
│  :5173 MCP Sessions │  :19876 WebUI (本服务)       │
│  (claude-sessions-  │                            │
│   mcp 内置 Web)      │  会话/项目 ← 代理 MCP ✅     │
│                     │  Skills 管理 ✅             │
│  路径 100% 正确      │  标签/重命名 ✅              │
│  (含中文目录名)      │  记忆查看 ✅                 │
│                     │  Windows 弹窗 ✅             │
│                     │  侧滑详情面板 ✅              │
└─────────────────────┴────────────────────────────┘
```

路径解析由 [claude-sessions-mcp](https://github.com/es6kr/claude-code-sessions) 的 `@claude-sessions/core` 保证正确。

## 依赖

| 依赖 | 用途 |
|------|------|
| Python 3.9+ + Flask | WebUI 后端 |
| Node.js + npm | claude-sessions-mcp（会话数据源） |

## 安装

```bash
# 1. 克隆
git clone https://github.com/hanasite/claude-code-webui.git ~/.claude/webui/

# 2. Python 依赖
pip install flask

# 3. Node.js 依赖（MCP Sessions 服务）
npm install --prefix ~/.claude/webui/ claude-sessions-mcp @claude-sessions/web

# 4. 启动
cd ~/.claude/webui
start start.bat
```

## 启动

### 方式一：一键启动（推荐）

双击桌面快捷方式 `Claude Code.lnk`，或：

```bash
cd ~/.claude/webui
start start.bat
```

### 方式二：分别启动

```bash
# 终端 1：MCP Sessions 服务（路径解析引擎，端口 5173）
cd ~/.claude/webui
npx @claude-sessions/web --port 5173

# 终端 2：WebUI（端口 19876）
cd ~/.claude/webui
python server.py
```

浏览器访问 `http://127.0.0.1:19876`

> **注意**：MCP 服务（5173）必须先启动，WebUI 依赖它获取正确的项目路径。

### 方式三：后台静默

```bash
# MCP Sessions 后台
cd ~/.claude/webui && node node_modules/@claude-sessions/web/dist/cli.js --port 5173 &

# WebUI 后台
pythonw server.py --no-browser
```

## 功能

| 模块 | 功能 |
|------|------|
| 📁 项目 | 按项目浏览，路径由 MCP 保证正确（含中文目录） |
| 💬 会话 | 分页查看消息、▶ 一键 resume（带 cd 到项目目录） |
| 🏷️ 标签 | 自定义标签，持久化到 labels.json |
| 🔍 搜索 | 跨项目全文搜索 |
| 📥 导出 | 会话导出为 Markdown |
| 🧠 Skills | 浏览已安装、搜索 SkillHub 一键安装、查看详情（侧滑面板） |
| 🧩 记忆 | 查看项目持久化记忆文件 |
| 🔔 弹窗 | Windows 原生弹窗通知（八爪鱼形象） |
| 🌙 主题 | 深色暗色主题，橙色八爪鱼配色 |

## 项目结构

```
~/.claude/webui/
├── server.py              # Flask 后端 API
├── templates/
│   └── index.html         # 单页前端（暗色主题 + 侧滑面板）
├── labels.json            # 会话标签持久化
├── node_modules/          # MCP Sessions 依赖
├── start.bat              # Windows 双击启动
├── start.vbs              # Windows 静默后台启动
├── CLAUDE.md              # Claude Code 自动部署指引
└── README.md
```

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端 SPA |
| `/api/projects` | GET | 项目列表（← 代理 MCP） |
| `/api/sessions/<project>` | GET | 会话列表（← 代理 MCP，支持 ?sort=） |
| `/api/session/<project>/<id>` | GET | 会话消息（分页） |
| `/api/session/<project>/<id>` | DELETE | 删除会话 |
| `/api/export/<project>/<id>` | GET | 导出 Markdown |
| `/api/search?q=` | GET | 跨项目搜索 |
| `/api/skills` | GET | 已安装 Skills / 搜索 SkillHub（?mode=search&q=） |
| `/api/skills/<name>` | GET | Skill 详情（SKILL.md 内容） |
| `/api/skills/install` | POST | 安装 Skill `{"slug":"..."}` |
| `/api/skills/<name>` | DELETE | 卸载 Skill |
| `/api/labels` | GET | 所有标签 |
| `/api/labels/<id>` | PUT/DELETE | 设置/删除标签 `{"label":"..."}` |
| `/api/memory/<project>` | GET | 项目记忆文件 |
| `/api/popup` | POST | Windows 弹窗通知 |

## 端口

| 端口 | 服务 | 说明 |
|------|------|------|
| 5173 | MCP Sessions Web | 会话数据源，路径解析引擎 |
| 19876 | WebUI | 主界面，Skills/标签/弹窗/记忆 |

## 集成到 Aemeath 桌宠

配合 [Aemeath](https://github.com/77wliNd/aemeath_withclaude) 桌宠使用：

- 🖱️ 右键宠物 → "📊 对话管理"
- 📌 系统托盘右键 → "📊 对话管理"

## License

MIT
