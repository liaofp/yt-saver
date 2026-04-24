#!/bin/bash
# ==========================================
# File: providers/onedrive.sh
# ==========================================

FILE_PATH="$1"
OD_TOKEN_JSON="$TOKEN"
CONF_PATH="/tmp/rclone_tmp.conf"

if [ ! -f "$FILE_PATH" ]; then
    echo "❌ 错误：找不到文件 $FILE_PATH"
    exit 1
fi

# 1. 尝试安装/检查 rclone
if ! command -v rclone &> /dev/null; then
    curl https://rclone.org/install.sh | sudo bash
fi

# 2. 关键修复：从 Token JSON 中提取 drive_id (如果存在) 并生成基础配置
# 如果 rclone token 是完整的，它可能已经包含了 drive_id
mkdir -p ~/.config/rclone

# 先写一个基础配置
cat <<EOF > "$CONF_PATH"
[tmp_od]
type = onedrive
token = $OD_TOKEN_JSON
EOF

echo "[*] 正在自动检索 OneDrive 驱动器信息..."

# 3. 自动补全配置：通过 rclone about 触发驱动器发现逻辑
# rclone 会尝试连接并获取 drive_id 和 drive_type，我们将其追加到配置文件
DRIVE_INFO=$(rclone --config "$CONF_PATH" backend driveid tmp_od: 2>/dev/null)

if [ -n "$DRIVE_INFO" ]; then
    echo "drive_id = $DRIVE_INFO" >> "$CONF_PATH"
    echo "drive_type = personal" >> "$CONF_PATH"
    echo "✅ 已自动获取 Drive ID: $DRIVE_INFO"
else
    # 如果无法自动获取，强制指定 personal 尝试（兼容旧版本）
    echo "drive_type = personal" >> "$CONF_PATH"
    echo "⚠️ 无法自动获取 Drive ID，尝试以个人版模式运行..."
fi

echo "[*] 开始上传..."

# 4. 执行上传
# 使用 -vv 可以看到更详细的调试信息
rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -vv

# 5. 获取 Item ID
# 注意：如果目录不存在，lsf 可能会报错，这里加一个容错
ITEM_ID=$(rclone --config "$CONF_PATH" lsf tmp_od:uploads/ --format "i" --files-only | head -n 1)
FILE_NAME=$(basename "$FILE_PATH")

if [ -z "$ITEM_ID" ]; then
    echo "❌ 错误：上传后无法获取文件 ID，请检查云端 uploads 目录"
    rm -f "$CONF_PATH"
    exit 1
fi

rm -f "$CONF_PATH"

echo -e "\n---RESULT_START---"
echo "ITEM_ID: $ITEM_ID"
echo "FILE_NAME: $FILE_NAME"
echo "---RESULT_END---\n"