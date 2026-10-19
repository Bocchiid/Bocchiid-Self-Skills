# 执行自动化：CLI、GUI、截图、隔离、恢复

## 策略

| 步骤 | 默认 | 说明 |
| --- | --- | --- |
| 命令/脚本/数据 | CLI | 快、可复现；可见终端里跑，方便截图 |
| 必须看界面/点按钮 | GUI | UIA/键鼠；动作前后截图；还原人做实验 |
| 物理/本人签字/线下 | 人工 | 生成操作卡，暂停 |
| 需要 WSL/Linux | 先问 | 不擅自装系统包/驱动/服务 |

**不强制 WSL/Linux**；用户机器上有什么就用什么。CLI 与 GUI 不互相冒充证据。

## CLI

```bash
python scripts/actions.py --workspace <WS> run \
  --step S1 --env local --autonomy assist --timeout 120 \
  --command "<命令>"
```

- `allow/confirm/deny`；confirm 先问用户；
- 输出进 `_worker/logs/<id>.stdout.txt` / `.stderr.txt`；
- 需要截图用可见终端：

```bash
python scripts/desktop.py --workspace <WS> terminal-run \
  --window "<终端标题>" --shell powershell \
  --command "<单行命令>" --log "<可见日志>" --timeout 120 --clear
```

- 截图只截命令 + 关键输出 + 提示符。

## GUI

1. `desktop.py list-windows` 找窗口；
2. `desktop.py uia --action list` 看控件；
3. 写动作 JSON：`target` + `expect` + `before/after`；
4. `desktop.py act --file ...`；
5. 只有 `status=ok` 才算完成。

动作必须“先验证窗口/控件，再动作，再验证状态变化”；坐标点击 `--confirm`。
不要盲点、不点未知弹窗、不替用户登录/提交。

## 截图只截核心

| 场景 | 截什么 | 不截什么 |
| --- | --- | --- |
| 代码 | 改动段/关键函数/报错行 + 文件名/行号 | 整个 IDE/整个文件 |
| 终端 | 命令 + 关键输出 + 提示符 | 整屏历史/无关窗口 |
| GUI | 目标对话框/面板/关键字段 | 整个桌面 |
| 拓扑/装置 | 全景 + 关键标识 | 无关背景 |

流程：

```bash
# 1) 窗口/全屏截图
python scripts/capture.py --workspace <WS> shot \
  --out Pictures/_raw/S8.png --window "<标题>"

# 2) 看原图，确定核心区域后裁剪
python scripts/capture.py --workspace <WS> crop \
  --in Pictures/_raw/S8.png --out Pictures/S8_核心.png \
  --box "x,y,w,h"
```

- 保留能证明应用/版本/路径的标题栏；
- 不用网图/生成图；不 P 图；
- 截图合格但结果不符：先排错，不重拍同样结果。

## 环境隔离

- Python 依赖只进任务 `.venv`；`actions.py run` 自动优先用；
- `capture.py`/`desktop.py`/`verify.py` 缺依赖时用任务 venv 重跑；
- 环境变量用 `--env-var`/`--env-file`，只作用于子进程；
- 不 `setx`、不改 profile/系统变量、不全局 `pip install`；
- 系统包：不在宿主装；WSL/VM 内先问用户。

## 崩溃与日志

- 状态/证据原子写 + `.bak`；
- 动作 intent/pid；结果写后清 intent；
- `_worker/logs/session.log`、`events.jsonl`、每动作 stdout/stderr；
- `worker.py logs --rotate` 按大小轮转，不自动删除；
- `worker.py doctor` 检查残留/心跳/损坏/超预算；
- 恢复顺序：doctor → 处理 in-flight → status/next；不重新 init。

## 进程安全

- 不关闭/杀宿主 Agent 的终端/IDE/进程；
- 宽范围 `taskkill /IM powershell`、`Stop-Process -Name ...`、`pkill python` 直接拒绝；
- 精确 PID 也要确认；目标是自己/父进程链/宿主进程 → 拒绝；
- 只清理自己开且记录 PID/标题的测试窗口；不确定就问用户。

## 依赖缺失

- 缺三个 skill：先问安装/复制，缺依赖不硬跑；
- 缺 Python 包：列出安装清单，问用户；同意后进任务 venv；
- 缺 Word COM：`.doc` 说明限制，用 LibreOffice/`.docx`；
- 缺 GUI/截图后端：降级人工截图或 CLI 文本证据。
