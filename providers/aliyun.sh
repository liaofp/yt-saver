#!/bin/bash
python3 -c "
from aligo import Aligo
ali = Aligo(refresh_token='$2')
folder = ali.get_folder_by_path('YT_Temp', create_when_empty=True)
res = ali.upload_file('$1', parent_file_id=folder.file_id)
print(f'---RESULT_START---\nDRIVE_ID: {res.drive_id}\nFILE_ID: {res.file_id}\nFILE_NAME: {res.name}\n---RESULT_END---')
"