#!/bin/bash
python3 -c "
import os, sys
sys.path.append(os.getcwd())
from aliclient import AliClient
ali = AliClient(refresh_token='$2')
res = ali.upload_file('$1')
print(f'---RESULT_START---\nDRIVE_ID: {res.drive_id}\nFILE_ID: {res.file_id}\nFILE_NAME: {res.name}\n---RESULT_END---')
"