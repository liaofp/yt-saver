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

# 3. Execute upload; abort on failure WITHOUT printing a result block,
#    so the local side knows the upload failed instead of retrieving garbage
if ! rclone --config "$CONF_PATH" copy "$FILE_PATH" tmp_od:uploads/ -v --onedrive-chunk-size 10M --transfers 1; then
    fail "rclone upload failed for $FILE_PATH"
fi

FILE_NAME=$(basename "$FILE_PATH")

# 4. Verify the upload: the remote item must exist and its size must match.
#    OneDrive Personal occasionally stores uploads with size 0 (server-side
#    metadata glitch); without this check a corrupted item would be reported
#    as a success and the local retrieval would fail with
#    "corrupted on transfer: sizes differ".
LOCAL_SIZE=$(stat -c %s "$FILE_PATH")
REMOTE_JSON=$(rclone --config "$CONF_PATH" lsjson "tmp_od:uploads/$FILE_NAME" 2>/dev/null)
REMOTE_SIZE=$(echo "$REMOTE_JSON" | jq -r '.[0].Size // empty' 2>/dev/null)

if [ -z "$REMOTE_SIZE" ]; then
    fail "upload verification failed - remote file not found: $FILE_NAME"
fi

if [ "$REMOTE_SIZE" != "$LOCAL_SIZE" ]; then
    # Remove the broken remote item so it cannot shadow future runs
    rclone --config "$CONF_PATH" deletefile "tmp_od:uploads/$FILE_NAME" > /dev/null 2>&1 || true
    fail "upload verification failed - size mismatch (local: $LOCAL_SIZE, remote: $REMOTE_SIZE), broken cloud file removed"
fi

# 5. Obtain Item ID of the uploaded file (matched by name, not "first item in folder")
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
