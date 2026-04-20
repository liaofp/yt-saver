#!/bin/bash
FILE_PATH=$1

# 获取服务器并上传
SERVER=$(curl -s https://api.gofile.io/servers | jq -r '.data.servers[0].name // "store1"')
RESPONSE=$(curl -F "file=@${FILE_PATH}" "https://${SERVER}.gofile.io/contents/uploadfile")

# 提取链接
DOWNLOAD_PAGE=$(echo $RESPONSE | jq -r '.data.downloadPage')

echo "---RESULT_START---"
echo "DL_URL: $DOWNLOAD_PAGE"
echo "---RESULT_END---"