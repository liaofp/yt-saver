#!/bin/bash
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
FILE_PATH="$1"
REFRESH_TOKEN="$2"

python3 -c "
import os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from aliclient import AlipanClient
try:
    ali = AlipanClient(refresh_token='$REFRESH_TOKEN')
    res = ali.upload_file('$FILE_PATH')
    # 安全获取属性
    d_id = res.get('drive_id')
    f_id = res.get('file_id')
    f_name = os.path.basename('$FILE_PATH')
    print(f'---RESULT_START---\nDRIVE_ID: {d_id}\nFILE_ID: {f_id}\nFILE_NAME: {f_name}\n---RESULT_END---')
except Exception as e:
    print(f'ERROR: {str(e)}', file=sys.stderr)
    sys.exit(1)
"