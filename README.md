# Claude Code User-Level Configuration

个人 Claude Code 用户级配置合集，包含常用技能和辅助脚本。

## 内容

| 文件 | 说明 |
|------|------|
| `CLAUDE.md` | 用户级指令（识图、联网搜索、Word/OPJU 文档、高危审批） |
| `skills/opju-extract/` | Origin OPJU 数据提取技能 |
| `skills/sync-to-github/` | GitHub 配置同步/备份技能（含隐私保护） |
| `scripts/vision.js` | 千问 VL 识图（需自行提供 API Key） |
| `scripts/websearch.py` | DuckDuckGo 联网搜索（免费，无需 Key） |
| `scripts/read_docx.py` | Word 文档读取 |
| `scripts/opju_extract.py` | Origin OPJU 数据提取工具 |

## 安装

### Windows (PowerShell)
```powershell
.\install.ps1
```

### Linux / WSL / macOS
```bash
chmod +x install.sh && ./install.sh
```

安装脚本会：
1. 将文件复制到 `~/.claude/` 目录
2. 自动更新 `CLAUDE.md` 中的脚本路径
3. 安装所需 Python 依赖
4. **不会覆盖**已有的 `settings.json`

## 前置条件

- **vision.js**：需注册[阿里云百炼](https://bailian.console.aliyun.com/) 获取 API Key，设为环境变量 `VISION_API_KEY`
- **opju_extract.py**：需安装 Origin/OriginPro + `pip install originpro pandas`
- **websearch.py**：需 `pip install ddgs`
- **read_docx.py**：需 `pip install python-docx`

## 自行配置

安装后请设置你自己的 API Key：

```powershell
# Windows
$env:VISION_API_KEY = "sk-你的千问API密钥"
```

```bash
# Linux/macOS
export VISION_API_KEY="sk-你的千问API密钥"
```

建议写入 `~/.bashrc` 或 `~/.zshrc` 以持久化。

## 自定义

- 如需修改 Claude Code 模型配置，编辑 `~/.claude/settings.json`
- 如需添加新的用户规则，编辑 `~/.claude/CLAUDE.md`
- 如需添加新技能，在 `~/.claude/skills/` 下创建新目录

## License

MIT
