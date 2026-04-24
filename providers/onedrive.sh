#!/bin/bash
# ==========================================
# File: providers/onedrive.sh
# ==========================================

FILE_PATH="$1"
# 此时 OD_CONFIG 包含的是完整的 ini 内容
OD_CONFIG="$TOKEN"
CONF_PATH="/tmp/rclone_tmp.conf"

if [ ! -f "$FILE_PATH" ]; then
    echo "❌ 错误：找不到文件 $FILE_PATH"
    exit 1
fi

# 1. 直接将完整的配置写入临时文件
echo "$OD_CONFIG" > "$CONF_PATH"

# 2. 这里的 [onedrive] 必须与你本地 config show 出来的中括号名称一致
# 建议在写入时统一强制修改中括号名称为 tmp_od 以便脚本后续调用
sed -i 's/\[.*\]/\[tmp_od\]/' "$CONF_PATH"

echo "[*] 开始上传 (使用完整本地配置)..."

# 3. 执行上传
rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -v

# 4. 获取 Item ID
ITEM_ID=$(rclone --config "$CONF_PATH" lsf tmp_od:uploads/ --format "i" --files-only | head -n 1)
FILE_NAME=$(basename "$FILE_PATH")

if [ -z "$ITEM_ID" ]; then
    echo "❌ 错误：上传失败或无法获取文件 ID"
    rm -f "$CONF_PATH"
    exit 1
fi

rm -f "$CONF_PATH"

echo -e "\n---RESULT_START---"
echo "ITEM_ID: $ITEM_ID"
echo "FILE_NAME: $FILE_NAME"
echo "---RESULT_END---\n"