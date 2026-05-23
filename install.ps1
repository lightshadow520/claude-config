# Claude Code 用户级配置安装脚本 (Windows)
# 用法: .\install.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeDir = "$env:USERPROFILE\.claude"
$ScriptsDir = "$ClaudeDir\scripts"
$SkillsDir = "$ClaudeDir\skills"

Write-Host "=== Claude Code 配置安装 ===" -ForegroundColor Cyan
Write-Host ""

# 1. Create directories
Write-Host "[1/5] 创建目录..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $ScriptsDir | Out-Null
New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null

# 2. Copy scripts
Write-Host "[2/5] 复制脚本到 $ScriptsDir ..." -ForegroundColor Yellow
Copy-Item -Force "$ScriptDir\scripts\*" $ScriptsDir\

# 3. Copy skills
Write-Host "[3/5] 复制技能到 $SkillsDir ..." -ForegroundColor Yellow
Copy-Item -Force -Recurse "$ScriptDir\skills\*" $SkillsDir\

# 4. Handle CLAUDE.md
Write-Host "[4/5] 设置 CLAUDE.md ..." -ForegroundColor Yellow
$TemplateClaude = "$ScriptDir\CLAUDE.md"
$UserClaude = "$ClaudeDir\CLAUDE.md"

if (Test-Path $UserClaude) {
    Write-Host "  已存在 $UserClaude，合并内容..." -ForegroundColor Gray
    # Append new content after existing, with separator
    $existing = Get-Content $UserClaude -Raw -Encoding UTF8
    $newContent = Get-Content $TemplateClaude -Raw -Encoding UTF8
    # Replace placeholder paths with actual scripts dir
    $newContent = $newContent -replace '<scripts_dir>', $ScriptsDir.Replace('\', '/')
    if ($existing -notmatch "opju_extract") {
        Add-Content $UserClaude "`n`n---`n`n"
        Add-Content $UserClaude $newContent
        Write-Host "  已追加新内容" -ForegroundColor Green
    } else {
        Write-Host "  OPJU 相关规则已存在，跳过" -ForegroundColor Gray
    }
} else {
    $newContent = Get-Content $TemplateClaude -Raw -Encoding UTF8
    $newContent = $newContent -replace '<scripts_dir>', $ScriptsDir.Replace('\', '/')
    $newContent | Out-File $UserClaude -Encoding UTF8
    Write-Host "  已创建 $UserClaude" -ForegroundColor Green
}

# 5. Install Python dependencies
Write-Host "[5/5] 安装 Python 依赖..." -ForegroundColor Yellow
$packages = @("ddgs", "python-docx", "pandas")
foreach ($pkg in $packages) {
    Write-Host "  pip install $pkg ..." -ForegroundColor Gray
    pip install $pkg 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    警告: $pkg 安装可能失败，请手动执行 pip install $pkg" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "请设置以下环境变量（可选但推荐）：" -ForegroundColor Yellow
Write-Host '  $env:VISION_API_KEY = "sk-你的千问API密钥"' -ForegroundColor White
Write-Host ""
Write-Host "如需 OPJU 提取功能，请安装 Origin/OriginPro 后执行：" -ForegroundColor Yellow
Write-Host "  pip install originpro" -ForegroundColor White
Write-Host ""
Write-Host "下次启动 Claude Code 时生效。" -ForegroundColor Cyan
