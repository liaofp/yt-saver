#!/bin/bash
# ==========================================
# File: providers/onedrive.sh
# Description: 利用系统预装的 rclone 实现自动刷新 Token 上传
# ==========================================

FILE_PATH="$1"
OD_TOKEN_JSON="$TOKEN" # 从环境变量读取 GitHub Secret

# 检查文件
if [ ! -f "$FILE_PATH" ]; then
    echo "❌ 错误：找不到文件 $FILE_PATH"
    exit 1
fi

# 1. 验证 rclone 是否可用
if ! command -v rclone &> /dev/null; then
    echo "⚠️ 环境中未找到 rclone，正在尝试动态安装..."
    curl https://rclone.org/install.sh | sudo bash
fi

# 2. 准备临时配置文件 (使用自定义路径，避免冲突)
CONF_PATH="/tmp/rclone_tmp.conf"
cat <<EOF > "$CONF_PATH"
[tmp_od]
type = onedrive
token = $OD_TOKEN_JSON
drive_type = personal
EOF

echo "[*] 开始上传至 OneDrive (由 rclone 托管 Token 刷新)..."

# 3. 使用 --config 参数执行上传
# rclone 会自动处理 4MB 限制、断点续传和 Token 刷新
rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -v

# 4. 获取上传后的 ID
# 微软 API 只有获取到这个 ID，本地才能精准回传
ITEM_ID=$(rclone --config "$CONF_PATH" lsf tmp_od:uploads/ --format "i" --files-only | head -n 1)
FILE_NAME=$(basename "$FILE_PATH")

if [ -z "$ITEM_ID" ]; then
    echo "❌ 错误：上传成功但无法检索到文件 ID"
    rm -f "$CONF_PATH"
    exit 1
fi

# 5. 清理临时配置并打印结果
rm -f "$CONF_PATH"

echo -e "\n---RESULT_START---"
echo "ITEM_ID: $ITEM_ID"
echo "FILE_NAME: $FILE_NAME"
echo "---RESULT_END---\n"