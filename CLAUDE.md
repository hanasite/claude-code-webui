# Claude Code WebUI — 对话管理与 Skills 管理器

浏览器端管理 Claude Code 对话历史、搜索会话、导出 Markdown、安装和管理 Skills。

## Claude Code 自动部署

当用户分享本仓库链接并要求部署时，按以下步骤操作：

### 1. 部署到本地

```bash
# 克隆到 ~/.claude/webui/
git clone https://github.com/hanasite/claude-code-webui.git ~/.claude/webui/

# 安装依赖
pip install flask

# 启动（静默后台运行）
cd ~/.claude/webui
pythonw server.py --no-browser
```

### 2. 验证

```bash
curl -s http://127.0.0.1:19876/api/projects
```

返回 JSON 项目列表即成功。

### 3. 创建快捷方式（可选）

```powershell
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Claude Code WebUI.lnk')
$sc.TargetPath = "$env:USERPROFILE\.claude\webui\start.bat"
$sc.WorkingDirectory = "$env:USERPROFILE\.claude\webui"
$sc.Save()
```

### 4. 打开浏览器

```bash
start http://127.0.0.1:19876
```

## 功能

| 模块 | 说明 |
|------|------|
| 📁 项目 | 浏览所有项目，查看会话数/大小 |
| 💬 会话 | 分页查看消息、Markdown 导出、删除 |
| 🔍 搜索 | 跨项目全文搜索 |
| 🏷️ 标签 | 自定义会话标签 |
| 🧠 Skills | 浏览已安装、搜索 SkillHub、安装/卸载 |

## API 端口

`http://127.0.0.1:19876`

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/projects` | GET | 项目列表 |
| `/api/sessions/<project>` | GET | 会话列表 |
| `/api/session/<project>/<id>` | GET/DELETE | 会话详情/删除 |
| `/api/export/<project>/<id>` | GET | 导出 Markdown |
| `/api/search?q=` | GET | 搜索 |
| `/api/skills` | GET | Skills 列表/搜索 |
| `/api/skills/install` | POST | 安装 Skill |
| `/api/skills/<name>` | DELETE | 卸载 Skill |
| `/api/labels` | GET/PUT/DELETE | 标签管理 |
| `/api/memory/<project>` | GET | 项目记忆 |

## 集成 Aemeath 桌宠

配合 [Aemeath](https://github.com/77wliNd/aemeath_withclaude) 使用，右键宠物 → "📊 对话管理" 一键打开本 WebUI。

## 项目结构

```
~/.claude/webui/
├── server.py         # Flask 后端
├── templates/
│   └── index.html    # 单页前端（暗色主题）
├── labels.json       # 标签持久化
├── setup.bat         # 一键部署脚本
├── start.bat         # 双击启动
├── start.vbs         # 静默后台启动
└── CLAUDE.md
```
