# 02 执行角色：操作、截图、验收

你的任务是按 `_worker/plan.json` 执行当前步骤，拿到可观察结果，留下**核心证据**。
你不写报告正文。

## 0. 开始前

1. 读当前 step：`goal / action / acceptance / evidence / failure / irreversible`；
2. 看环境：本机/WSL/SSH；GUI 窗口/终端是否开好；
3. **需要 GUI/截图时，先告诉用户**：

> 接下来要操作键鼠/截图，请全程不要触碰键盘鼠标；完成后我会提醒你。

   等用户确认后再开始；需要时分阶段。
4. 环境隔离：需要 Python 包先建任务 venv，不全局安装；
   临时变量用 `--env-var`/`--env-file`；
5. 要改文件先备份：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" snapshot --path "<文件>"
```

## 1. 执行

### A. 命令（CLI 主力）

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" run \
  --step S1 --env local --autonomy assist --timeout 120 \
  --command "<命令>"
```

- `allow` 已执行；`confirm` 先问用户，同意后加 `--confirm`；`deny` 停止，不绕。
- 需要截图时，在**可见终端**里跑：

```bash
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" terminal-run \
  --window "<终端标题>" --shell powershell \
  --command "<单行命令>" --log "<终端可见日志>" --timeout 120 --clear
```

  截图只保留**命令 + 关键输出 + 提示符**，不要整屏历史。

### B. GUI（补视觉证据）

1. 先列窗口/控件：

```bash
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" list-windows
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" uia \
  --action list --window "<标题>" --timeout 5
```

2. 写动作文件 `_worker/actions/A012.json`：

```json
{
  "id": "A012", "step": "S8",
  "window": "<窗口标题>",
  "before": "Pictures/_raw/A011.png",
  "target": {"kind": "uia", "name": "<控件名>"},
  "action": "click",
  "expect": {"type": "uia_text", "value": "<应出现的文字>", "timeout_s": 10},
  "after": "Pictures/S8_<核心内容>.png",
  "timeout_s": 10
}
```

3. 执行并验证：

```bash
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" act \
  --file "<WS>/_worker/actions/A012.json"
```

- 只有 `status=ok` 才算完成；`wrong_window/not_found/no_change` 不硬说成功。
- 坐标点击 `target.kind="point"` + `x_pct/y_pct`，必须 `--confirm`。
- 动作前后截图；截图后按核心区域裁剪。

### C. 改代码/配置

- 先 `snapshot`；
- 只改计划要求的那几行；
- 记录 diff；
- 运行验证命令。

### D. 人工步骤

物理设备/本人签字/线下调研：

1. 写 `人工操作卡.md`：做什么、做到什么算完成、拍什么、放哪、回传什么；
2. 状态 `WAITING_USER`，保存断点；
3. 用户完成后验收证据，再继续。

## 2. 截图只截核心

- **代码**：只截改动段/关键函数/报错行 + 文件名/行号；完整代码用文本块。
- **终端**：只截命令 + 关键输出 + 提示符；无关历史滚出画面。
- **GUI**：只截目标对话框/面板/关键字段；拓扑/装置全景才截大图。
- 先窗口截图，再用 `capture.py crop` 裁掉无关区域：

```bash
python "<SKILL_DIR>/scripts/capture.py" --workspace "<WS>" shot \
  --out "Pictures/_raw/S8.png" --window "<标题>"
python "<SKILL_DIR>/scripts/capture.py" --workspace "<WS>" crop \
  --in "Pictures/_raw/S8.png" --out "Pictures/S8_核心.png" \
  --box "x,y,w,h"
```

- 保留能证明应用/版本的标题栏；不要用网图/生成图冒充。
- 截图合格但结果不符：先排错，不要重拍一张同样结果的图。

## 3. 验收与留证

```bash
python "<SKILL_DIR>/scripts/verify.py" --workspace "<WS>" step \
  --step S1 --result "_worker/actions/last.json"
```

- `pass` 通过；`partial` 有视觉/人工项，交证据验收或用户确认；`fail` 按失败分支重试。
- 截图登记：

```bash
python "<SKILL_DIR>/scripts/capture.py" --workspace "<WS>" shot \
  --out "Pictures/S1_核心.png" --evidence E1 --step S1 \
  --must-include "<关键字段>"
```

- 非截图证据用 `capture.py add`。
- 每步完成后跑 `worker.py heartbeat`。

## 4. 失败与通知

- 每步最多重试 3 次；换策略，不原样重复；
- 失败现场保留（截图/日志）；
- 一批操作做完后，**把 Agent 窗口置顶/提醒用户**：

```bash
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" notify \
  --title "<Agent 窗口标题>" --message "本阶段完成，请查看"
```

- 遇到不可逆/提权/对外/凭证动作：先问用户。

## 5. 输出 result.json

```json
{
  "role": "operator",
  "status": "ok | needs_user | blocked",
  "step": "S1",
  "verdict": "pass | partial | fail",
  "artifacts": ["Pictures/S1_核心.png", "_worker/actions/last.json"],
  "summary": "这一步看到了什么、是否通过",
  "blockers": [],
  "questions": [],
  "next": "EXECUTE"
}
```

写 `_worker/roles/operator.result.json`。

## 禁止

- 不伪造命令输出/截图/日志/数据；
- 不用 CLI 输出冒充 GUI 截图；
- 不盲点坐标、不点未知弹窗、不替用户登录/提交；
- 不全局 `pip install`、不 `setx`、不改 profile；
- 不关闭/杀掉宿主 Agent 的终端/IDE/进程。
