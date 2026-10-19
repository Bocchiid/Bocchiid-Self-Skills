# 自动化执行：GUI、命令、截图、远程

## 原则

v0.1 优先**用 GUI 模拟人做实验**，而不是把所有 GUI 步骤替换成 CLI。选择规则：

| 步骤 | 首选 | 备选 |
| --- | --- | --- |
| 指导书要求 GUI 证据（MiniEdit/Wireshark/IDE/浏览器） | 控件树 | 视觉坐标 + 键鼠；再不行人工 |
| 本身是命令行（mininet/OVS/ping/脚本） | CLI | 可见终端输入并截图 |
| 环境准备/数据校验/批处理 | CLI | — |
| 物理设备/本人签字/线下调研 | 人工接管 | — |

**证据保真**：模板要 Wireshark 界面截图，就不能用 `tshark` 输出替代；CLI 可以辅助验证，
但不能冒充 GUI 证据。

## Windows

### 截图

- `capture.py` 用 Pillow `ImageGrab`，DPI 感知；窗口截图用 pywin32 取窗口矩形后裁剪。
- 200% 缩放时，非 DPI 感知进程看到 1440×900，物理屏幕是 2880×1800；混用会错位。
  `capture.py` 启动时会设 Per-Monitor DPI 感知。
- 备选：PowerShell `System.Windows.Forms` + `System.Drawing`。

### GUI

- 窗口枚举/聚焦：pywin32。
- 控件树：`uia.ps1`（PowerShell `UIAutomationClient`）。
- 键鼠：pywin32 `keybd_event` / `mouse_event`；文本优先剪贴板 + Ctrl+V。
- 可选增强：`pywinauto`（更稳的控件树）、`mss`（多屏）、`opencv-python`（模板匹配）。

### 可见终端

- 打开 Windows Terminal / PowerShell / WSL 终端；
- `desktop.py terminal-run` 把命令包成：

```powershell
& { <command> } 2>&1 | Tee-Object -FilePath '<log>'; Write-Output '<marker>:'$LASTEXITCODE
```

- 轮询日志，等 `<marker>:$?`；
- 截终端窗口；
- 终端驱动不了 → 人工截图卡，**不合成假图**。

## Linux guest（VM / WSLg）

- host 通过 SSH 调用 `guest_agent.py`；
- guest 依赖：Python 3、`xdotool`、`wmctrl`、`scrot`（或 `gnome-screenshot`）；
- 截图落 guest，`scp` 回 `<WS>/Pictures/`；
- X11 优先；Wayland 下 xdotool 可能不可用，用 `grim` 截图、`ydotool` 输入（v0.2）；
- OVS 内核态/WSLg 不稳定时，优先完整 Linux VM，先快照再跑。

## macOS

- 截图：`screencapture`；
- GUI：AppleScript/System Events；需要在“系统设置 → 隐私与安全性 → 辅助功能”授权；
- 可选 `pyautogui`。

## 截图规范

- 全屏/窗口/区域三种；默认窗口，保留标题栏；
- 文件名带步骤/内容/日期；
- 不裁剪关键字段；
- 不覆盖旧图；重名 `_v2`；
- 原始文件与标注文件分开；
- 敏感信息先打码再上传/读图。

## 动作验证

每个 GUI 动作都带 `expect`：

```json
{"type": "uia_text", "value": "Buffer ID", "timeout_s": 10}
{"type": "screenshot_changed", "threshold": 0.005}
{"type": "file_exists", "path": "Data/flow.dump"}
{"type": "manual", "description": "用户确认弹窗已出现"}
```

- `uia_text`：等控件名包含该文本；
- `uia_control`：等控件出现；
- `screenshot_changed`：前后截图差异超过阈值；
- `file_exists`：文件落盘；
- `manual`：必须用户确认。

动作返回 `ok|wrong_window|not_found|no_change|needs_user`。只有 `ok` 才算完成。

## 安全

- 动作前确认前台窗口标题；不匹配不执行；
- 坐标点击必须 `--confirm`；
- 删除/覆盖/提交/安装/提权类 GUI 动作单独确认；
- 不点未知弹窗、不关闭不认识的窗口、不替用户登录；
- 所有动作进 `actions.jsonl`，含时间、命令、退出码、截图路径、SHA256。

## 环境隔离与进程安全

- Python 依赖只进 `<WS>/.venv`；`actions.py run` 自动优先用 venv；
- 环境变量用 `--env-var` / `--env-file`，只作用于子进程；
- 不改全局 PATH、系统环境变量、shell profile；
- 不在宿主装系统包/驱动/服务；
- **不关闭/杀掉宿主 Agent 的终端、IDE 或进程**；宽范围 `taskkill`/`Stop-Process`/`pkill`
  会被拒绝；只清理自己打开且记录 PID/标题的测试窗口。

详见 `environment-isolation.md`。
