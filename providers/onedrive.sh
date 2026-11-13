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
SINGLE_LIMIT=$((250 * 1024 * 1024))

# Extract the OAuth access token from the rclone config; needed for the
# single-request upload fallback below.
ACCESS_TOKEN=$(grep '^token' "$CONF_PATH" | sed 's/^token *= *//' | jq -r '.access_token // empty' 2>/dev/null)

# Single-request upload via Graph simple upload (PUT ...:/content).
# Bypasses upload sessions entirely; works around Microsoft currently
# rejecting upload-session chunk PUTs with 401 BadContextToken:
# https://github.com/rclone/rclone/issues/10328
upload_single() {
    local enc_name code
    enc_name=$(jq -rn --arg f "$FILE_NAME" '$f|@uri' 2>/dev/null)
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 30 --max-time 900 \
        -X PUT "https://graph.microsoft.com/v1.0/me/drive/root:/uploads/${enc_name}:/content" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/octet-stream" \
        --data-binary @"${FILE_PATH}")
    [ "$code" = "201" ] || [ "$code" = "200" ]
}

# 3. Upload with retries and verification.
#    Each attempt: multipart via rclone first, then (for files < 250MB) fall
#    back to single-request upload if multipart fails. Every "success" is
#    verified by comparing the remote size with the local one, because
#    OneDrive Personal sometimes stores broken size-0 items.
UPLOAD_OK=0
USE_SINGLE=0
for attempt in 1 2 3; do
    COPIED=0
    if [ "$USE_SINGLE" -eq 0 ]; then
        echo "[*] Upload attempt $attempt (multipart via rclone)..."
        if rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -v --onedrive-chunk-size 10M --transfers 1 --retries 1; then
            COPIED=1
        fi
    fi
    if [ "$COPIED" -eq 0 ] && [ "$LOCAL_SIZE" -lt "$SINGLE_LIMIT" ] && [ -n "$ACCESS_TOKEN" ]; then
        if [ "$USE_SINGLE" -eq 0 ]; then
            echo "[*] Multipart upload failed; falling back to single-request upload..."
        else
            echo "[*] Upload attempt $attempt (single-request)..."
        fi
        if upload_single; then
            COPIED=1
        fi
    fi
    if [ "$COPIED" -eq 1 ]; then
        REMOTE_JSON=$(rclone --config "$CONF_PATH" lsjson "tmp_od:uploads/$FILE_NAME" 2>/dev/null)
        REMOTE_SIZE=$(echo "$REMOTE_JSON" | jq -r '.[0].Size // empty' 2>/dev/null)
        if [ -n "$REMOTE_SIZE" ] && [ "$REMOTE_SIZE" = "$LOCAL_SIZE" ]; then
            UPLOAD_OK=1
            break
        fi
        # Reported success but the remote item is broken (e.g. size 0)
        rclone --config "$CONF_PATH" deletefile "tmp_od:uploads/$FILE_NAME" > /dev/null 2>&1 || true
        echo "[!] Upload verification failed (local: $LOCAL_SIZE, remote: ${REMOTE_SIZE:-missing}); broken item removed."
        # Next attempt goes straight to the single-request upload
        USE_SINGLE=1
    else
        echo "[!] Upload attempt $attempt failed."
    fi
    if [ "$attempt" -lt 3 ]; then
        echo "[*] Retrying in 30s..."
        sleep 30
    fi
done

if [ "$UPLOAD_OK" -ne 1 ]; then
    fail "upload failed verification after 3 attempts (OneDrive upload sessions may be degraded; single-request fallback only supports files < 250MB)"
fi

# 4. Obtain Item ID of the uploaded file (matched by name, not "first item in folder")
ITEM_ID=$(echo "$REMOTE_JSON" | jq -r '.[0].ID // empty' 2>/dev/null)

if [ -z "$ITEM_ID" ]; then
    fail "upload completed but unable to extract file ID"
fi

# 5. Cleanup and output result
rm -f "$CONF_PATH"

echo -e "\n---RESULT_START---"
echo "ITEM_ID: $ITEM_ID"
echo "FILE_NAME: $FILE_NAME"
echo "---RESULT_END---"
