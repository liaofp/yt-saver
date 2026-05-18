#!/bin/bash
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
FILE_PATH="$1"
REFRESH_TOKEN="$2"

# Force unbuffered Python stdout to avoid GitHub log stalling
python3 -u -c "
import os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from aliclient import AlipanClient

try:
    token = os.environ.get('TOKEN')
    if not token:
        raise Exception('Aliyun Drive token not received')
    # 1. Initialize client (drive_id is fetched internally)
    ali = AlipanClient(refresh_token=token)

    # 2. Execute upload (supports rapid-upload logic)
    res = ali.upload_file('$FILE_PATH')

    # 3. Core fix: read drive_id directly from the ali instance to avoid dict access errors
    d_id = ali.drive_id
    f_id = res['file_id']
    f_name = os.path.basename('$FILE_PATH')

    # 4. Print standardized output for local AliyunProvider parsing
    print(f'---RESULT_START---\nDRIVE_ID: {d_id}\nFILE_ID: {f_id}\nFILE_NAME: {f_name}\n---RESULT_END---')

except Exception as e:
    print(f'❌ Upload failed: {str(e)}', file=sys.stderr)
    sys.exit(1)
"
