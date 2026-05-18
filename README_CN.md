# yt-saver

通过 GitHub Actions 远程下载 YouTube 视频/音频，并自动转存到第三方云存储的框架。用户只需在 `providers/` 目录下提供新的存储实现，即可在 `tasks.yml` 中切换存储后端，完成整个工作流。

---

## 功能特性

- **远程下载**：利用 GitHub Actions 运行器绕过本地 IP 限制。
- **可插拔存储**：支持阿里云盘、OneDrive、Gofile，或任意自定义存储提供商。
- **批量任务**：在 `tasks.yml` 中定义多个下载任务，一键批量执行。
- **Cookie 自动化**：内置 Playwright 辅助脚本，自动登录 YouTube 并导出 `cookies.txt`。
- **隐私优先**：每次任务结束后自动删除 GitHub Actions 运行记录。

---

## 快速开始

### 1. 前置要求

- Python 3.8+
- 已安装并登录的 [GitHub CLI (`gh`)](https://cli.github.com/)
- [uv](https://docs.astral.sh/uv/)（推荐）或 `pip`
-（可选）[rclone](https://rclone.org/) — 仅在本地回传 OneDrive 文件时需要

### 2. 安装依赖

```bash
uv venv .venv
source .venv/bin/activate
uv pip install pyyaml requests playwright
```

### 3. 单任务（命令行）

```bash
# 默认下载音频到 OneDrive
python3 youtube.py <YOUTUBE_URL>

# 下载视频到阿里云盘
python3 youtube.py <YOUTUBE_URL> --mode video --storage aliyun --token <REFRESH_TOKEN>

# 自定义文件名（不要带扩展名）
python3 youtube.py <YOUTUBE_URL> --filename my_song
```

### 4. 批量任务（YAML）

编辑 `tasks.yml`：

```yaml
config:
  mode: "audio"          # audio | video
  storage: "onedrive"    # onedrive | aliyun | gofile
  branch: "main"
  verbose: true
  # token: "your_token"  # 使用 aliyun 时必须填写

tasks:
  "https://www.youtube.com/watch?v=EXAMPLE1": "song_one"
  "https://www.youtube.com/watch?v=EXAMPLE2":
    filename: "song_two"
    mode: "video"
```

执行：

```bash
python3 main.py
```

---

## 项目架构

```
.
├── youtube.py              # 单任务入口：解析参数 → 触发 Actions → 监控 → 回传
├── main.py                 # 批量入口：读取 tasks.yml，循环调用 youtube.py 逻辑
├── utils.py                # Playwright 辅助：自动登录 YouTube → 导出 Netscape cookies.txt
├── tasks.yml               # 批量任务配置文件
├── cookies.txt             # YouTube Cookie（可选，Git 忽略）
├── .github/workflows/
│   └── download.yml        # GitHub Actions Workflow 定义
└── providers/              # 云存储提供商插件目录
    ├── base.py             # 抽象基类 StorageProvider
    ├── aliyun.py           # 阿里云盘 Provider（本地回传 + 云端删除）
    ├── aliclient.py        # 阿里云盘 Open API 客户端（Token 刷新、分片上传/下载）
    ├── aliyun.sh           # GitHub Actions 内调用的阿里云盘上传脚本
    ├── onedrive.py         # OneDrive Provider（本地回传 + 云端删除，依赖 rclone）
    ├── odclient.py         # OneDrive Graph API 客户端（分片上传、流式下载）
    ├── onedrive.sh         # GitHub Actions 内调用的 OneDrive 上传脚本
    ├── gofile.py           # Gofile Provider（仅打印下载链接，不回传）
    └── gofile.sh           # GitHub Actions 内调用的 Gofile 上传脚本
```

### 工作流程

1. **本地触发** — `youtube.py` 调用 `gh workflow run` 启动远程工作流。
2. **远程下载** — GitHub Actions 安装 `yt-dlp`，下载媒体文件，并通过 `providers/<name>.sh` 上传到指定云端。
3. **结果交换** — Shell 脚本打印标准化结果块：
   ```
   ---RESULT_START---
   KEY: VALUE
   ---RESULT_END---
   ```
4. **本地回传** — 对应的 `providers/<name>.py` 解析日志中的结果块，将文件下载到 `~/Downloads`（可配置），然后删除云端临时文件。
5. **清理** — 删除本次 GitHub Actions 运行记录，实现无痕处理。

---

## 二次开发：添加新的存储提供商

以添加 `mystorage` 为例：

1. **实现本地回传处理器** — 创建 `providers/mystorage.py`：

   ```python
   import re
   from .base import StorageProvider

   class MystorageProvider(StorageProvider):
       def handle_result(self, logs, token=None):
           match = re.search(r"---RESULT_START---(.*?)---RESULT_END---", logs, re.S)
           if not match:
               return
           data = match.group(1)
           # 解析字段，下载到 self.download_dir，然后清理云端文件
   ```

2. **实现远程上传脚本** — 创建 `providers/mystorage.sh`：

   ```bash
   #!/bin/bash
   FILE_PATH="$1"
   # 将 $FILE_PATH 上传到你的云存储服务
   echo "---RESULT_START---"
   echo "MY_KEY: my_value"
   echo "---RESULT_END---"
   ```

3. **在 `youtube.py` 中注册** — 导入 `MystorageProvider` 并在 `monitor_workflow` 中添加分支：

   ```python
   elif storage_type == "mystorage":
       MystorageProvider(config).handle_result(log_stdout, token)
   ```

4. **注册命令行选项** — 在 `setup_args()` 的 `--storage` 的 `choices` 中加入 `"mystorage"`。

5. **注册 Workflow 选项** — 在 `.github/workflows/download.yml` 的 `storage_provider` 输入选项中加入 `"mystorage"`。

---

## 安全提示

- `cookies.txt` 包含敏感的 YouTube 登录凭证，已被 `.gitignore` 排除，切勿提交到仓库。
- Workflow 在 `always()` 步骤中删除 Cookie 和下载文件，但 Token 等信息仍可能出现在日志中；本地脚本会在最后删除运行记录。
- `youtube.py` 中的命令执行使用了 `shell=True`，请避免直接传入不可信的外部输入。

---

## 许可证

MIT License
