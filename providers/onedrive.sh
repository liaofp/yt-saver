#!/bin/bash
# ==========================================
# File: providers/onedrive.sh
# ==========================================

FILE_PATH="$1"
OD_CONFIG="$TOKEN"
CONF_PATH="/tmp/rclone_tmp.conf"

if [ ! -f "$FILE_PATH" ]; then
    echo "❌ 错误：找不到文件 $FILE_PATH"
    exit 1
fi

# 1. 检查并静默安装 rclone
if ! command -v rclone &> /dev/null; then
    echo "[*] 环境中未找到 rclone，正在安装..."
    # 使用官方脚本进行非交互式安装
    curl https://rclone.org/install.sh | sudo bash > /dev/null 2>&1
fi

# 2. 写入完整配置
echo "$OD_CONFIG" > "$CONF_PATH"
# 统一配置块名称
sed -i 's/\[.*\]/\[tmp_od\]/' "$CONF_PATH"

echo "[*] 开始上传 (rclone v$(rclone version --short))..."

# 3. 执行上传
rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -v --onedrive-chunk-size 10M --transfers 1

# 4. 获取 Item ID (用于本地回传)
ITEM_ID=$(rclone --config "$CONF_PATH" lsf tmp_od:uploads/ --format "i" --files-only | head -n 1)
FILE_NAME=$(basename "$FILE_PATH")

if [ -z "$ITEM_ID" ]; then
    echo "❌ 错误：上传完成但无法提取文件 ID"
    rm -f "$CONF_PATH"
    exit 1
fi

# 5. 清理并输出结果
rm -f "$CONF_PATH"

echo -e "\n---RESULT_START---"
echo "ITEM_ID: $ITEM_ID"
echo "FILE_NAME: $FILE_NAME"
echo "---RESULT_END---\n"