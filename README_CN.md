# yt-saver

通过 GitHub Actions 远程下载 YouTube 视频/音频，通过第三方云存储将文件运回本地的框架。用户只需在 `providers/` 目录下提供新的存储实现，即可在 `tasks.yml` 中切换存储后端，完成整个工作流。

> ⚠️ **使用前提**：你必须拥有一个 **GitHub 账号**，并** Fork 本仓库**到你自己的账号下，才能触发 GitHub Actions Workflow 并写入 Secrets。所有后续操作均在 Fork 后的个人仓库中进行。

> **为什么用 GitHub Actions？**
> 很多地区直接访问 YouTube 受限。本项目利用 GitHub Actions 运行器的海外 IP 完成下载，再通过云存储中转回本地，全程无需在本地运行 yt-dlp，也无需代理。

---

## 功能特性

- **远程下载**：利用 GitHub Actions 运行器绕过本地 IP 限制。
- **可插拔存储**：支持阿里云盘、OneDrive、Gofile，或任意自定义存储提供商。
- **批量任务**：在 `tasks.yml` 中定义多个下载任务，一键批量执行。
- **Cookie 自动化**：内置 Playwright 辅助脚本，自动登录 YouTube 并导出 `cookies.txt`。
- **隐私优先**：每次任务结束后自动删除 GitHub Actions 和第三方存储运行记录。

---

## 快速开始

### 1. 准备 GitHub 仓库

使用本项目前，你必须先完成以下两步：

1. **注册 GitHub 账号**：若还没有，请前往 [github.com](https://github.com) 注册。
2. **Fork 本仓库**：点击本页面右上角的 **Fork** 按钮，将仓库复制到你自己的 GitHub 账号下。所有后续操作（触发 Actions、设置 Secrets、下载文件）均在**你 Fork 后的个人仓库**中进行。

Fork 完成后，将仓库克隆到本地：

```bash
git clone https://github.com/<你的用户名>/yt-saver.git
cd yt-saver
```

### 2. 前置要求

- **Python 3.8+**
- **GitHub CLI (`gh`)** — 必须已安装并登录，且对你 Fork 的仓库有 workflow / secrets 写入权限
- **uv**（推荐）或 `pip`
- **rclone** — 使用 **OneDrive** 时必须安装（本地回传与云端清理均依赖它）

### 3. 安装依赖

```bash
uv venv .venv
source .venv/bin/activate
uv pip install pyyaml requests playwright
```

> 若使用 `pip`，将上述 `uv pip install` 替换为 `pip install pyyaml requests playwright` 即可。

### 4. 配置 OneDrive（推荐默认存储）

OneDrive 是本项目的**默认推荐存储**，配置一次即可长期使用。请按以下步骤完成 rclone 与 OneDrive 的整合。

#### 步骤一：安装 rclone

| 平台 | 命令 / 方式 |
|------|-------------|
| **Windows** | 1. 下载 [rclone 安装包](https://rclone.org/downloads/)<br>2. 解压后将 `rclone.exe` 所在目录加入系统 `PATH`<br>3. 打开 PowerShell 执行 `rclone version` 验证 |
| **Linux** | `sudo -v && curl https://rclone.org/install.sh | sudo bash`<br>执行 `rclone version` 验证 |
| **macOS** | `brew install rclone`（需先安装 [Homebrew](https://brew.sh/)） |

#### 步骤二：配置 rclone 远程（OneDrive）

在终端执行以下命令，按交互提示完成授权：

```bash
rclone config
```

关键选项说明：

1. 选择 `n` 新建远程（remote）。
2. **name** 必须填写 `onedrive`（本项目固定读取该名称）。
3. **Storage** 选择 `Microsoft OneDrive`（通常输入序号 `31` 或 `onedrive`）。
4. **client_id** / **client_secret**：直接回车留空，使用 rclone 内置默认即可。
5. **region**：选择你的 OneDrive 区域（全球版选 `1` Global）。
6. 程序会弹出浏览器让你登录微软账号并授权；授权成功后回到终端按提示完成。
7. 最后选择 `y` 保存配置。

验证配置是否成功：

```bash
rclone lsd onedrive:
```

若能列出你的 OneDrive 根目录文件夹，说明配置完成。

> **提示**：`rclone config` 生成的配置文件位于 `~/.config/rclone/rclone.conf`（Windows 为 `%USERPROFILE%\.config\rclone\rclone.conf`），其中包含刷新令牌。请勿将该文件提交到 Git 仓库。

#### 步骤三：创建 GitHub Secret（供 Actions 上传使用）

GitHub Actions 运行器同样需要访问你的 OneDrive。最简单的方式是将 rclone 配置中的令牌同步为仓库 Secret：

1. 打开你的 rclone 配置文件，找到 `[onedrive]` 区块下的 `token = {...}` 整行 JSON。
2. 在本地仓库目录执行：

```bash
gh secret set ONEDRIVE_TOKEN < ~/.config/rclone/rclone.conf
```

> Windows 用户可手动复制 `rclone.conf` 内容，然后执行 `gh secret set ONEDRIVE_TOKEN`，粘贴后按 `Ctrl+D`（或 `Ctrl+Z` + 回车）结束输入。

完成以上三步后，OneDrive 即可作为默认存储使用。

---

## 使用指南

### 单任务（命令行）

```bash
# 默认下载音频到 OneDrive（最简用法）
python3 youtube.py <YOUTUBE_URL>

# 下载视频到 OneDrive
python3 youtube.py <YOUTUBE_URL> --mode video

# 自定义文件名（不要带扩展名，yt-dlp 会自动追加）
python3 youtube.py <YOUTUBE_URL> --filename my_song

# 下载到阿里云盘（需 refresh_token）
python3 youtube.py <YOUTUBE_URL> --mode audio --storage aliyun --token <REFRESH_TOKEN>

# 使用 Gofile（仅返回下载链接，不回传本地）
python3 youtube.py <YOUTUBE_URL> --storage gofile
```

### 批量任务（YAML）

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

> `tasks.yml` 支持两种任务格式：
> - 简单格式：`"URL": "文件名"`（mode 继承全局 config）
> - 完整格式：`"URL": {filename: "xxx", mode: "audio"}`（逐项解析，缺失项继承全局）

---

## 分平台详细指南

### Windows

#### 环境准备

1. **安装 Python 3.8+**
   - 从 [python.org](https://www.python.org/downloads/) 下载安装包，安装时勾选 **"Add Python to PATH"**。
   - 验证：`python --version`

2. **安装 GitHub CLI (`gh`)**
   - 从 [GitHub CLI  releases](https://github.com/cli/cli/releases) 下载 `.msi` 安装包。
   - 安装后打开 **PowerShell** 执行：
     ```powershell
     gh auth login
     ```
     按提示选择 `GitHub.com` → `HTTPS` → 浏览器授权登录。

3. **安装 uv（可选但推荐）**
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

4. **安装 rclone（使用 OneDrive 必需）**
   - 下载 [rclone 安装包](https://rclone.org/downloads/)，解压后将目录加入系统 `PATH`。
   - 验证：`rclone version`

5. **配置 rclone OneDrive 远程**
   ```powershell
   rclone config
   ```
   - 新建 remote，**name 必须为 `onedrive`**。
   - 按提示完成微软账号授权。
   - 验证：`rclone lsd onedrive:`

6. **设置 GitHub Secret**
   ```powershell
   $conf = Get-Content "$env:USERPROFILE\.config\rclone\rclone.conf" -Raw
   $conf | gh secret set ONEDRIVE_TOKEN
   ```

#### 运行项目

```powershell
# 进入项目目录
cd yt-saver

# 创建虚拟环境并安装依赖
uv venv .venv
.venv\Scripts\activate
uv pip install pyyaml requests playwright

# 单任务示例
python youtube.py "https://www.youtube.com/watch?v=xxxx" --mode audio

# 批量任务
python main.py
```

> **注意**：Windows 下 `python3` 命令可能不可用，请使用 `python` 或 `py`。

### Linux

#### 环境准备

1. **安装 Python 3.8+**
   - Ubuntu/Debian：
     ```bash
     sudo apt update && sudo apt install -y python3 python3-venv python3-pip
     ```
   - Fedora：
     ```bash
     sudo dnf install -y python3 python3-venv python3-pip
     ```
   - Arch：
     ```bash
     sudo pacman -S python python-venv python-pip
     ```
   - 验证：`python3 --version`

2. **安装 GitHub CLI (`gh`)**
   - Ubuntu/Debian：
     ```bash
     sudo mkdir -p -m 755 /etc/apt/keyrings
     wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
     sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
     echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
     sudo apt update && sudo apt install -y gh
     ```
   - Fedora：
     ```bash
     sudo dnf install -y gh
     ```
   - Arch：
     ```bash
     sudo pacman -S github-cli
     ```
   - 登录：
     ```bash
     gh auth login
     ```

3. **安装 uv（可选但推荐）**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source $HOME/.local/bin/env
   ```

4. **安装 rclone（使用 OneDrive 必需）**
   ```bash
   sudo -v && curl https://rclone.org/install.sh | sudo bash
   rclone version
   ```

5. **配置 rclone OneDrive 远程**
   ```bash
   rclone config
   ```
   - 新建 remote，**name 必须为 `onedrive`**。
   - 按提示完成微软账号授权。
   - 验证：`rclone lsd onedrive:`

6. **设置 GitHub Secret**
   ```bash
   gh secret set ONEDRIVE_TOKEN < ~/.config/rclone/rclone.conf
   ```

#### 运行项目

```bash
# 进入项目目录
cd yt-saver

# 创建虚拟环境并安装依赖
uv venv .venv
source .venv/bin/activate
uv pip install pyyaml requests playwright

# 单任务示例
python3 youtube.py "https://www.youtube.com/watch?v=xxxx" --mode audio

# 批量任务
python3 main.py
```

> **注意**：首次运行 `main.py` 时若未检测到 `cookies.txt`，会自动调用 Playwright 打开浏览器引导你登录 YouTube。登录成功后 Cookie 会自动保存并同步到 GitHub Secret。

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
- rclone 配置文件包含 OneDrive 刷新令牌，请妥善保管，不要上传到公开仓库。

---

## 免责声明

本项目仅供**个人学习和技术交流**使用，严禁用于任何商业或违法用途。

用户利用本项目代码所产生的一切后果（包括但不限于版权纠纷、账号封禁、数据丢失、隐私泄露等）均由用户自行承担，与项目原始作者及贡献者无关。请在使用前确保你遵守当地法律法规及 YouTube、GitHub 等平台的服务条款。

---

## 许可证

MIT License
