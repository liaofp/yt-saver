#!/bin/bash
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
FILE_PATH="$1"
REFRESH_TOKEN="$2"

# 使用 -u 参数强制刷新 Python 标准输出，避免 GitHub 日志卡顿
python3 -u -c "
import os, sys
sys.path.insert(0, '$SCRIPT_DIR')
from aliclient import AlipanClient

try:
    token = os.environ.get('TOKEN')
    if not token:
        raise Exception('未接收到阿里网盘 Token')
    # 1. 初始化客户端（内部已获取 drive_id）
    ali = AlipanClient(refresh_token=token)
    
    # 2. 执行上传 (支持秒传逻辑)
    res = ali.upload_file('$FILE_PATH')
    
    # 3. 核心修复：直接从 ali 实例获取 drive_id，避免访问字典报错
    d_id = ali.drive_id
    f_id = res['file_id']
    f_name = os.path.basename('$FILE_PATH')
    
    # 4. 打印标准输出供本地 AliyunProvider 解析
    print(f'---RESULT_START---\nDRIVE_ID: {d_id}\nFILE_ID: {f_id}\nFILE_NAME: {f_name}\n---RESULT_END---')

except Exception as e:
    print(f'❌ 上传失败: {str(e)}', file=sys.stderr)
    sys.exit(1)
"