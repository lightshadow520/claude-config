#!/usr/bin/env bash
# Claude Code 用户级配置安装脚本 (Linux / macOS / WSL)
# 用法: chmod +x install.sh && ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
SKILLS_DIR="$CLAUDE_DIR/skills"
COMPCHEM_DIR="$CLAUDE_DIR/comp-chem"

echo -e "\033[36m=== Claude Code 配置安装 ===\033[0m"
echo ""

# 1. Create directories
echo -e "\033[33m[1/6] 创建目录...\033[0m"
mkdir -p "$SCRIPTS_DIR"
mkdir -p "$SKILLS_DIR"
mkdir -p "$COMPCHEM_DIR"

# 2. Copy scripts
echo -e "\033[33m[2/6] 复制脚本到 $SCRIPTS_DIR ...\033[0m"
cp -f "$SCRIPT_DIR/scripts/"* "$SCRIPTS_DIR/"

# 3. Copy skills
echo -e "\033[33m[3/6] 复制技能到 $SKILLS_DIR ...\033[0m"
cp -rf "$SCRIPT_DIR/skills/"* "$SKILLS_DIR/"

# 4. Copy comp-chem domain files
echo -e "\033[33m[4/6] 复制领域文件到 $COMPCHEM_DIR ...\033[0m"
cp -f "$SCRIPT_DIR/comp-chem/"* "$COMPCHEM_DIR/"

# 5. Handle CLAUDE.md
echo -e "\033[33m[5/6] 设置 CLAUDE.md ...\033[0m"
TEMPLATE_CLAUDE="$SCRIPT_DIR/CLAUDE.md"
USER_CLAUDE="$CLAUDE_DIR/CLAUDE.md"

if [ -f "$USER_CLAUDE" ]; then
    echo "  已存在 $USER_CLAUDE，检查是否需要合并..."
    if ! grep -q "opju_extract" "$USER_CLAUDE" 2>/dev/null; then
        echo "" >> "$USER_CLAUDE"
        echo "---" >> "$USER_CLAUDE"
        echo "" >> "$USER_CLAUDE"
        sed -e "s|<scripts_dir>|$SCRIPTS_DIR|g" -e "s|<config_dir>|$CLAUDE_DIR|g" "$TEMPLATE_CLAUDE" >> "$USER_CLAUDE"
        echo -e "\033[32m  已追加新内容\033[0m"
    else
        echo "  OPJU 相关规则已存在，跳过"
    fi
else
    sed -e "s|<scripts_dir>|$SCRIPTS_DIR|g" -e "s|<config_dir>|$CLAUDE_DIR|g" "$TEMPLATE_CLAUDE" > "$USER_CLAUDE"
    echo -e "\033[32m  已创建 $USER_CLAUDE\033[0m"
fi

# 6. Install Python dependencies
echo -e "\033[33m[6/6] 安装 Python 依赖...\033[0m"
pip install ddgs python-docx pandas 2>/dev/null || echo -e "\033[31m  部分包安装失败，请手动执行: pip install ddgs python-docx pandas\033[0m"

echo ""
echo -e "\033[32m=== 安装完成 ===\033[0m"
echo ""
echo -e "\033[33m请设置以下环境变量（可选但推荐）：\033[0m"
echo -e '  export VISION_API_KEY="sk-你的千问API密钥"'
echo ""
echo "建议将上述 export 语句添加到 ~/.bashrc 或 ~/.zshrc"
echo ""
echo -e "\033[33m如需 OPJU 提取功能，请安装 Origin/OriginPro 后执行：\033[0m"
echo "  pip install originpro"
echo ""
echo -e "\033[36m下次启动 Claude Code 时生效。\033[0m"
