#!/bin/bash
# 
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
FILE_PATH="$1"
REFRESH_TOKEN="$2"

python3 -c "
import os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from aliclient import AlipanClient

try:
    # 1. 初始化客户端（此处会自动获取 drive_id 并打印成功日志）
    ali = AlipanClient(refresh_token='$REFRESH_TOKEN')
    
    # 2. 执行上传
    res = ali.upload_file('$FILE_PATH')
    
    # 3. 关键修复：从 ali 实例获取 drive_id，从本地获取文件名
    # 不要从 res 字典里取，因为 complete 接口返回的内容不确定
    d_id = ali.drive_id
    f_id = res.get('file_id')
    f_name = os.path.basename('$FILE_PATH')
    
    if not f_id:
        raise Exception('上传成功但未获取到 File ID')

    # 4. 打印标准输出供 AliyunProvider 解析 
    print(f'---RESULT_START---\nDRIVE_ID: {d_id}\nFILE_ID: {f_id}\nFILE_NAME: {f_name}\n---RESULT_END---')

except Exception as e:
    print(f'\n❌ 上传过程发生错误: {str(e)}', file=sys.stderr)
    sys.exit(1)
"