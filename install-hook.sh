#!/bin/bash
# 安装 pre-push code review hook 到任意项目
# 用法: bash install-hook.sh [项目路径]
# 示例: bash install-hook.sh /c/code/my-java-project

set -e

TARGET="${1:-.}"

if [ ! -d "$TARGET/.git" ]; then
    echo "错误: $TARGET 不是一个 git 仓库"
    exit 1
fi

HOOK_PATH="$TARGET/.git/hooks/pre-push"

cat > "$HOOK_PATH" << 'HOOK_EOF'
#!/bin/bash
# ============================================================
# Code Review Pre-Push Hook
# 每次 git push 前自动检查，发现严重问题阻止 push
# 跳过审查: git push --no-verify  或  git push -n
# ============================================================

set -e

# ---- 读取 push 的目标 ----
while read local_ref local_sha remote_ref remote_sha; do
  if [ "$remote_sha" = "0000000000000000000000000000000000000000" ]; then
    RANGE="$local_sha^..$local_sha"
  else
    RANGE="$remote_sha..$local_sha"
  fi
done

[ -z "$RANGE" ] && exit 0

# ---- 检查是否有 Java 文件 ----
JAVA_FILES=$(git diff --name-only --diff-filter=AM "$RANGE" 2>/dev/null | grep '\.java$' || true)
[ -z "$JAVA_FILES" ] && exit 0

FILE_COUNT=$(echo "$JAVA_FILES" | wc -l)

echo ""
echo "┌──────────────────────────────────────────────┐"
echo "│  🔍 Pre-Push Code Review                     │"
echo "│  检查 $FILE_COUNT 个 Java 文件                        │"
echo "└──────────────────────────────────────────────┘"
echo ""

# ---- 变更摘要 ----
echo "变更文件:"
echo "$JAVA_FILES" | while read f; do echo "  • $f"; done
echo ""

# ---- 尝试 Claude Code 自动审查 ----
if command -v claude &> /dev/null; then
    echo "⏳ 正在运行 AI 代码审查..."
    DIFF_FILE=$(mktemp)
    git diff "$RANGE" > "$DIFF_FILE"

    REVIEW_OUTPUT=$(claude -p "请审查以下 git diff，对照 references/BE_CODE_STANDARD.md 规范，只报告置信度>=80的问题。如果发现编译错误或会导致NPE/数据丢失的问题，标记为🔴必须修复。如果没有严重问题，输出'PASS'。" < "$DIFF_FILE" 2>&1 || true)
    rm -f "$DIFF_FILE"

    echo "$REVIEW_OUTPUT"

    if echo "$REVIEW_OUTPUT" | grep -q "🔴.*必须修复\|CRITICAL"; then
        echo ""
        echo "┌──────────────────────────────────────────────┐"
        echo "│  🚫 Push 已阻止                              │"
        echo "│  发现必须修复的问题，请修复后重新 push        │"
        echo "│  或使用 git push --no-verify 强制跳过        │"
        echo "└──────────────────────────────────────────────┘"
        exit 1
    fi
else
    echo "⚠️  claude CLI 未安装，跳过自动 AI 审查"
    echo "   请在 push 前在 Claude Code 中运行: /code-review"
    echo ""
fi

echo "✅ 审查通过"
exit 0
HOOK_EOF

chmod +x "$HOOK_PATH"
echo "✅ Hook 已安装到: $HOOK_PATH"
echo ""
echo "现在每次 git push 前会自动触发代码审查。"
echo "如需跳过: git push --no-verify"
