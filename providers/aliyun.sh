#!/bin/bash
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
python3 -c "
import os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from aliclient import AlipanClient
ali = AlipanClient(refresh_token='$2')
res = ali.upload_file('$1')
print(f'---RESULT_START---\nDRIVE_ID: {res.drive_id}\nFILE_ID: {res.file_id}\nFILE_NAME: {res.name}\n---RESULT_END---')
"