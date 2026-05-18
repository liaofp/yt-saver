#!/bin/bash
# ==========================================
# File: providers/onedrive.sh
# ==========================================

FILE_PATH="$1"
OD_CONFIG="$TOKEN"
CONF_PATH="/tmp/rclone_tmp.conf"

if [ ! -f "$FILE_PATH" ]; then
    echo "❌ Error: file not found $FILE_PATH"
    exit 1
fi

# 1. Check and silently install rclone
if ! command -v rclone &> /dev/null; then
    echo "[*] rclone not found in environment, installing..."
    # Non-interactive installation via official script
    curl https://rclone.org/install.sh | sudo bash > /dev/null 2>&1
fi

# 2. Write full configuration
echo "$OD_CONFIG" > "$CONF_PATH"
# Normalize config block name
sed -i 's/\[.*\]/\[tmp_od\]/' "$CONF_PATH"

echo "[*] Starting upload (rclone v$(rclone version --short))..."

# 3. Execute upload
rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -v --onedrive-chunk-size 10M --transfers 1

# 4. Obtain Item ID (for local retrieval)
ITEM_ID=$(rclone --config "$CONF_PATH" lsf tmp_od:uploads/ --format "i" --files-only | head -n 1)
FILE_NAME=$(basename "$FILE_PATH")

if [ -z "$ITEM_ID" ]; then
    echo "❌ Error: upload completed but unable to extract file ID"
    rm -f "$CONF_PATH"
    exit 1
fi

# 5. Cleanup and output result
rm -f "$CONF_PATH"

echo -e "\n---RESULT_START---"
echo "ITEM_ID: $ITEM_ID"
echo "FILE_NAME: $FILE_NAME"
echo "---RESULT_END---\n"
