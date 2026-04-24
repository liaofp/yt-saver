#!/bin/bash
# ==========================================
# File: providers/onedrive.sh
# Description: 在 GitHub Actions 中运行，负责上传文件到 OneDrive
# ==========================================

# 获取脚本所在目录，确保能正确导入 python 模块 [cite: 44]
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)
FILE_PATH="$1"      # 待上传的文件路径
OD_TOKEN_JSON="$2"  # 从 GitHub Secret 传入的 rclone 格式 Token JSON

# 检查文件是否存在 [cite: 24]
if [ ! -f "$FILE_PATH" ]; then
    echo "❌ 错误：找不到要上传的文件 $FILE_PATH"
    exit 1
fi

# 使用 python 执行上传逻辑，-u 参数确保日志实时输出 [cite: 44, 51]
python3 -u -c "
import os
import sys
import json

# 将当前目录加入搜索路径以导入 odclient [cite: 44]
sys.path.insert(0, '$SCRIPT_DIR')
from odclient import OneDriveClient

try:
    # 1. 初始化客户端
    # 直接将 GitHub Actions 传入的字符串解析为 JSON [cite: 11, 44]
    client = OneDriveClient('$OD_TOKEN_JSON')
    
    # 2. 执行上传
    # 注意：对于极大的文件（超过100MB），建议在 odclient 中实现分片上传 [cite: 25, 29]
    res = client.upload_file('$FILE_PATH')
    
    # 3. 提取结果
    item_id = res.get('id')
    f_name = res.get('name')
    
    if not item_id:
        raise Exception('上传成功但未获取到 Item ID')
    
    # 4. 打印标准输出供本地 Provider 解析 [cite: 42, 44]
    print('---RESULT_START---')
    print(f'ITEM_ID: {item_id}')
    print(f'FILE_NAME: {f_name}')
    print('---RESULT_END---')

except Exception as e:
    print(f'❌ OneDrive 远程上传失败: {str(e)}', file=sys.stderr)
    sys.exit(1)
"