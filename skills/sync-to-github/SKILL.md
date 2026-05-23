---
name: sync-to-github
description: Upload/sync user-level Claude Code configuration to GitHub. Use when user wants to upload configs, sync settings to GitHub, backup Claude Code setup, or share user-level capabilities as a public repo. Handles privacy protection (API key redaction) and path portability.
license: MIT
---

# Sync Claude Config to GitHub

Upload user-level Claude Code configuration to a GitHub repository with automatic privacy protection.

**Target repo:** `lightshadow520/claude-config` (https://github.com/lightshadow520/claude-config)

## Privacy & Path Protection Rules

### MUST redact before uploading

1. **API Keys**: Scan for patterns like `sk-*`, `Bearer *`, `token=*`, `key=*` in all files
   - `settings.json` → replace `ANTHROPIC_AUTH_TOKEN` value with `"your-deepseek-api-key-here"`
   - `vision.js` → replace hardcoded API key with `process.env.VISION_API_KEY || ""`
   - Any other `sk-` prefixed keys → replace with placeholder

2. **Absolute paths**: Distributed CLAUDE.md uses `<scripts_dir>` placeholder
   - Local CLAUDE.md has real paths like `C:\Users\polestar\.claude\scripts\`
   - Repo CLAUDE.md has `<scripts_dir>` (install script replaces at install time)

3. **Personal info**: Check for email addresses, real names in unexpected places

### MUST keep

- Skill definitions, script logic, install scripts → these are the product
- `.gitignore` to exclude `__pycache__/`, `.DS_Store`, `*.pyc`

## Repo Structure

```
claude-config/
├── CLAUDE.md              # User instructions (paths = <scripts_dir>)
├── README.md              # Setup guide for new users
├── settings.template.json # Example settings (no real keys)
├── skills/                # User-level skills
│   ├── opju-extract/SKILL.md
│   └── sync-to-github/SKILL.md
├── scripts/               # Tool scripts
│   ├── vision.js          # (API key → env var)
│   ├── websearch.py
│   ├── read_docx.py
│   └── opju_extract.py
├── install.ps1            # Windows installer
├── install.sh             # Linux/WSL installer
└── .gitignore
```

## Sync Procedure

### 1. Audit (always first)

```bash
# Scan for leaked keys
grep -rE 'sk-[a-zA-Z0-9]{20,}' <repo_dir>
# Scan for hardcoded paths
grep -rE '[A-Z]:\\' <repo_dir>
```

### 2. Sync files from local to repo

Copy the canonical versions from `~/.claude/` to the repo:

| Local source | Repo target | Transform |
|---|---|---|
| `~/.claude/CLAUDE.md` | `repo/CLAUDE.md` | Real paths → `<scripts_dir>` |
| `~/.claude/skills/*/` | `repo/skills/*/` | Copy as-is (paths already use `<scripts_dir>`) |
| `~/.claude/scripts/*` | `repo/scripts/*` | Copy as-is (keys already in env vars) |
| `~/.claude/settings.json` | `repo/settings.template.json` | Redact auth tokens |

### 3. Version and push

```bash
cd <repo_dir>
git add -A
git commit -m "vX.Y.Z: <what changed>"
git tag "vX.Y.Z"
git push --tags origin master
```

## Install Scripts

Both installers (`install.ps1`, `install.sh`) do the same thing:

1. Create `~/.claude/scripts/` and `~/.claude/skills/`
2. Copy scripts and skills from repo to `~/.claude/`
3. Replace `<scripts_dir>` in CLAUDE.md with detected `~/.claude/scripts` (platform-native path)
4. Merge new CLAUDE.md sections into existing `~/.claude/CLAUDE.md` (don't overwrite)
5. Install Python deps: `ddgs`, `python-docx`, `pandas`
6. Remind user to set `VISION_API_KEY` env var

## Version History

- **v1.0.0** — Initial release: CLAUDE.md, 4 scripts, opju-extract skill, installers
- **v1.0.1** — Add sync-to-github skill; CLAUDE.md paths fixed to `~/.claude/scripts/`
