#!/bin/bash
# ==========================================
# File: providers/onedrive.sh
# ==========================================

SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
FILE_PATH="$1"
# 关键改动：不再将 TOKEN 作为 $2 传递给 Python 参数，而是设为环境变量
export OD_TOKEN_RAW="$2"

if [ ! -f "$FILE_PATH" ]; then
    echo "❌ 错误：找不到文件 $FILE_PATH"
    exit 1
fi

# 使用 -u 强制无缓冲输出
python3 -u -c "
import os
import sys
import json

sys.path.insert(0, '$SCRIPT_DIR')
from odclient import OneDriveClient

try:
    # 从环境变量安全读取，避免 Shell 引用导致的截断
    token_str = os.environ.get('OD_TOKEN_RAW', '')
    if not token_str:
        raise Exception('未接收到 Token 字符串 (OD_TOKEN_RAW 为空)')

    client = OneDriveClient(token_str)
    res = client.upload_file('$FILE_PATH')
    
    item_id = res.get('id')
    f_name = res.get('name')
    
    if not item_id:
        raise Exception(f'上传异常，接口返回内容: {res}')
    
    # 打印标准输出供本地 Provider 解析
    print('\n---RESULT_START---')
    print(f'ITEM_ID: {item_id}')
    print(f'FILE_NAME: {f_name}')
    print('---RESULT_END---\n')

except Exception as e:
    # 打印详细错误到标准错误流
    print(f'❌ OneDrive 远程上传失败: {str(e)}', file=sys.stderr)
    sys.exit(1)
"