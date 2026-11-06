#!/bin/zsh -f
# 一键初始化 Git 仓库并上传到 GitHub (支持 gh CLI 或手动输入仓库地址)
set -e
DIR="${0:A:h}"
cd "$DIR"

echo "========================================================"
echo "  🚀 VanishCam for macOS — 一键上传到 GitHub 工具"
echo "========================================================"

# 清理不需要上传的缓存与临时文件
rm -rf __pycache__ .venv logs models .dmg_staging *.dmg 2>/dev/null || true

if [[ ! -d ".git" ]]; then
    echo "正在初始化本地 Git 仓库..."
    git init -b main
fi

git add .
if git diff --cached --quiet; then
    echo "当前没有新的文件更改需要提交。"
else
    git commit -m "feat: VanishCam for macOS with Goku Instant Transmission, Particles mode, global hotkey & .app bundle"
    echo "✅ 已完成本地代码提交 (Git Commit)。"
fi

echo ""
# 检查是否已配置 remote origin
if git remote get-url origin >/dev/null 2>&1; then
    ORIGIN_URL=$(git remote get-url origin)
    echo "检测到已绑定的远程仓库: $ORIGIN_URL"
    echo "正在推送到 GitHub..."
    git push -u origin main
    echo ""
    echo "🎉 上传成功！仓库地址: $ORIGIN_URL"
    exit 0
fi

# 检查是否安装了 GitHub CLI (gh) 且已登录
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    echo "检测到你已登录 GitHub CLI (gh)！"
    echo -n "请输入你想创建的 GitHub 仓库名称 [默认: vanish_webcam_macos]: "
    read REPO_NAME
    REPO_NAME=${REPO_NAME:-vanish_webcam_macos}
    echo "正在自动创建公开仓库并推送代码..."
    gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
    echo ""
    echo "🎉 自动创建并上传成功！"
    exit 0
fi

echo "请在浏览器打开 https://github.com/new 创建一个空仓库（不要勾选 Add a README）。"
echo -n "创建完成后，请粘贴你的 GitHub 仓库地址 (例如 https://github.com/你的用户名/vanish_webcam_macos.git): "
read REMOTE_URL

if [[ -z "$REMOTE_URL" ]]; then
    echo "❌ 未输入仓库地址，已取消推送。你可以稍后再次双击本脚本继续上传。"
    exit 1
fi

git remote add origin "$REMOTE_URL" 2>/dev/null || git remote set-url origin "$REMOTE_URL"
git branch -M main
echo "正在推送到 $REMOTE_URL ..."
git push -u origin main

echo ""
echo "🎉 恭喜！项目已成功上传到 GitHub: $REMOTE_URL"
read -k 1 "?按任意键关闭窗口..."
