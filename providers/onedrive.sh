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
LAST_HTTP_CODE=""

# Extract the OAuth access token from the rclone config; needed for the
# single-request upload fallback below. Must be re-read AFTER an rclone run,
# because rclone refreshes expired tokens and writes them back to the config.
get_access_token() {
    ACCESS_TOKEN=$(grep '^token' "$CONF_PATH" | sed 's/^token *= *//' | jq -r '.access_token // empty' 2>/dev/null)
}

# Single-request upload via Graph simple upload (PUT ...:/content).
# Bypasses upload sessions entirely; works around Microsoft currently
# rejecting upload-session chunk PUTs with 401 BadContextToken:
# https://github.com/rclone/rclone/issues/10328
upload_single() {
    local enc_name
    enc_name=$(jq -rn --arg f "$FILE_NAME" '$f|@uri' 2>/dev/null)
    LAST_HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 30 --max-time 900 \
        -X PUT "https://graph.microsoft.com/v1.0/me/drive/root:/uploads/${enc_name}:/content" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/octet-stream" \
        --data-binary @"${FILE_PATH}")
    [ "$LAST_HTTP_CODE" = "201" ] || [ "$LAST_HTTP_CODE" = "200" ]
}

# 3. Upload once: multipart via rclone, then (for files < 250MB) fall back to
#    a single-request upload if multipart fails. The result is verified by
#    comparing the remote size with the local one, because OneDrive Personal
#    sometimes stores broken size-0 items.
COPIED=0
echo "[*] Uploading via multipart (rclone)..."
if rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -v --onedrive-chunk-size 10M --transfers 1 --retries 1; then
    COPIED=1
else
    if [ "$LOCAL_SIZE" -lt "$SINGLE_LIMIT" ]; then
        get_access_token
        if [ -n "$ACCESS_TOKEN" ]; then
            echo "[*] Multipart upload failed; falling back to single-request upload..."
            if upload_single; then
                COPIED=1
            else
                echo "[!] Single-request upload failed (HTTP ${LAST_HTTP_CODE})."
            fi
        else
            echo "[!] Could not extract access token from config; single-request fallback unavailable."
        fi
    else
        echo "[!] File is >= 250MB; single-request fallback unavailable."
    fi
fi

UPLOAD_OK=0
if [ "$COPIED" -eq 1 ]; then
    REMOTE_JSON=$(rclone --config "$CONF_PATH" lsjson "tmp_od:uploads/$FILE_NAME" 2>/dev/null)
    REMOTE_SIZE=$(echo "$REMOTE_JSON" | jq -r '.[0].Size // empty' 2>/dev/null)
    if [ -n "$REMOTE_SIZE" ] && [ "$REMOTE_SIZE" = "$LOCAL_SIZE" ]; then
        UPLOAD_OK=1
    else
        # Reported success but the remote item is broken (e.g. size 0)
        echo "[!] Upload verification failed (local: $LOCAL_SIZE, remote: ${REMOTE_SIZE:-missing})."
    fi
fi

if [ "$UPLOAD_OK" -ne 1 ]; then
    # Cleanup: remove any broken/partial remote item, then fail without
    # printing a result block so the local side knows the upload failed
    rclone --config "$CONF_PATH" deletefile "tmp_od:uploads/$FILE_NAME" > /dev/null 2>&1 || true
    rm -f "$CONF_PATH"
    echo "❌ Error: upload failed and broken cloud item cleaned up (multipart 401 / single-request HTTP ${LAST_HTTP_CODE:-n/a})"
    exit 1
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
