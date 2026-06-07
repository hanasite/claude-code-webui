# Claude Code 对话管理 WebUI

浏览器端的 Claude Code 对话历史与 Skills 管理器。配合 [Aemeath 桌宠](https://github.com/77wliNd/aemeath_withclaude) 右键菜单一键打开。

## ⚡ Claude Code 一键部署

复制以下提示词发送给你的 Claude Code，自动完成部署：

```
请根据 https://github.com/hanasite/claude-code-webui/blob/master/CLAUDE.md 部署 Claude Code 对话管理 WebUI，包括克隆仓库、安装 Flask 依赖、启动服务并验证。
```

部署内容：git clone → `~/.claude/webui/` → pip install flask → 启动 → 打开浏览器

## 功能

| 模块 | 功能 |
|------|------|
| 📁 项目管理 | 按项目浏览所有对话，按时间/大小/消息数排序 |
| 💬 会话浏览 | 分页查看消息、Markdown 导出、一键删除 |
| 🏷️ 标签 | 为重要会话添加自定义标签 |
| 🔍 搜索 | 跨项目全文搜索对话内容 |
| 🧠 Skills | 浏览已安装 Skills、搜索 SkillHub 商店、一键安装/卸载 |
| 🔔 弹窗 | 调用 Windows 原生通知弹窗 |

## 一键部署

### Windows

双击 `setup.bat`，自动完成：
1. 安装 Python Flask 依赖
2. 创建桌面快捷方式
3. 启动 WebUI

### 手动部署

```bash
# 1. 安装依赖
pip install flask

# 2. 启动（两种方式）
python server.py              # 带终端窗口，Ctrl+C 停止
pythonw server.py --no-browser # 后台静默运行，手动打开 http://127.0.0.1:19876

# 3. 浏览器访问
start http://127.0.0.1:19876
```

## 部署到 Claude Code

将整个 `webui/` 目录放到 `~/.claude/webui/`：

```powershell
# PowerShell 一键部署
mkdir ~/.claude/webui -Force
Copy-Item -Recurse * ~/.claude/webui/
pip install flask
```

## 集成到 Aemeath 桌宠

WebUI 已原生集成到 [Aemeath](https://github.com/77wliNd/aemeath_withclaude) 桌宠（自 v2.1.0 起）：

- 🖱️ 右键宠物 → "📊 对话管理"
- 📌 系统托盘右键 → "📊 对话管理"

桌宠会自动检测 WebUI 运行状态，未运行时后台启动 `pythonw server.py`，然后打开浏览器。

## 开发

```bash
# 启动开发服务器（修改自动重载）
python server.py
# 访问 http://127.0.0.1:19876
```

### 项目结构

```
webui/
├── server.py          # Flask 后端 API
├── templates/
│   └── index.html     # 单页前端（暗色主题）
├── labels.json        # 会话标签持久化
├── start.bat          # Windows 双击启动
├── start.vbs          # Windows 静默后台启动
├── setup.bat          # 一键部署脚本
└── README.md
```

### API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/projects` | GET | 列出所有项目 |
| `/api/sessions/<project>` | GET | 列出项目会话 |
| `/api/session/<project>/<id>` | GET | 获取会话消息（分页） |
| `/api/session/<project>/<id>` | DELETE | 删除会话 |
| `/api/export/<project>/<id>` | GET | 导出 Markdown |
| `/api/search?q=` | GET | 跨项目搜索 |
| `/api/skills` | GET | 列出/搜索 Skills |
| `/api/skills/install` | POST | 安装 Skill |
| `/api/skills/<name>` | DELETE | 卸载 Skill |
| `/api/labels` | GET/PUT/DELETE | 会话标签 CRUD |
| `/api/memory/<project>` | GET | 获取项目记忆 |
| `/api/popup` | POST | Windows 通知弹窗 |

## License

MIT
