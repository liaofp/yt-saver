#!/bin/bash
# File: providers/onedrive.sh
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
FILE_PATH="$1"

# 检查文件
if [ ! -f "$FILE_PATH" ]; then
    echo "❌ 错误：找不到文件 $FILE_PATH"
    exit 1
fi

# 直接读取由 Workflow 注入的环境变量 TOKEN
python3 -u -c "
import os, sys, json
sys.path.insert(0, '$SCRIPT_DIR')
from odclient import OneDriveClient

try:
    # 获取环境变量 TOKEN
    token_str = os.environ.get('TOKEN', '')
    
    if not token_str:
        raise Exception('环境变量 TOKEN 为空，请检查 Workflow 中 env 段的配置')

    client = OneDriveClient(token_str)
    res = client.upload_file('$FILE_PATH')
    
    item_id = res.get('id')
    f_name = res.get('name')
    
    if not item_id:
        raise Exception(f'上传异常，接口返回: {res}')
    
    print('\n---RESULT_START---')
    print(f'ITEM_ID: {item_id}')
    print(f'FILE_NAME: {f_name}')
    print('---RESULT_END---\n')

except Exception as e:
    print(f'❌ OneDrive 远程上传失败: {str(e)}', file=sys.stderr)
    sys.exit(1)
"