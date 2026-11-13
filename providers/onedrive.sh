#!/bin/bash
# ==========================================
# File: providers/onedrive.sh
# ==========================================

FILE_PATH="$1"
OD_CONFIG="$TOKEN"
CONF_PATH="/tmp/rclone_tmp.conf"

fail() {
    echo "❌ Error: $1"
    rm -f "$CONF_PATH"
    exit 1
}

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

FILE_NAME=$(basename "$FILE_PATH")
LOCAL_SIZE=$(stat -c %s "$FILE_PATH")

# 3. Execute upload with retries.
#    OneDrive Personal upload sessions occasionally fail with HTTP 401
#    BadContextToken / 503 (Microsoft-side degradation), or even "succeed"
#    leaving a size-0 item. Each attempt is verified by comparing the remote
#    size with the local one; broken items are removed before retrying.
UPLOAD_OK=0
for attempt in 1 2 3; do
    if rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -v --onedrive-chunk-size 10M --transfers 1; then
        REMOTE_JSON=$(rclone --config "$CONF_PATH" lsjson "tmp_od:uploads/$FILE_NAME" 2>/dev/null)
        REMOTE_SIZE=$(echo "$REMOTE_JSON" | jq -r '.[0].Size // empty' 2>/dev/null)
        if [ -n "$REMOTE_SIZE" ] && [ "$REMOTE_SIZE" = "$LOCAL_SIZE" ]; then
            UPLOAD_OK=1
            break
        fi
        # rclone reported success but the remote item is broken (e.g. size 0)
        rclone --config "$CONF_PATH" deletefile "tmp_od:uploads/$FILE_NAME" > /dev/null 2>&1 || true
        echo "[!] Upload verification failed (local: $LOCAL_SIZE, remote: ${REMOTE_SIZE:-missing}); broken item removed."
    else
        echo "[!] Upload attempt $attempt failed (rclone copy error)."
    fi
    if [ "$attempt" -lt 3 ]; then
        echo "[*] Retrying in 30s..."
        sleep 30
    fi
done

if [ "$UPLOAD_OK" -ne 1 ]; then
    fail "upload failed verification after 3 attempts (OneDrive upload sessions may be degraded; retry later or use another storage provider)"
fi

# 4. Obtain Item ID of the uploaded file (matched by name, not "first item in folder")
ITEM_ID=$(echo "$REMOTE_JSON" | jq -r '.[0].ID // empty' 2>/dev/null)

if [ -z "$ITEM_ID" ]; then
    fail "upload completed but unable to extract file ID"
fi

# 6. Cleanup and output result
rm -f "$CONF_PATH"

echo -e "\n---RESULT_START---"
echo "ITEM_ID: $ITEM_ID"
echo "FILE_NAME: $FILE_NAME"
echo "---RESULT_END---"
