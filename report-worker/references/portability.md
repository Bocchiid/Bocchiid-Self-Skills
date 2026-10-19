# 跨 Agent / 跨平台适配

## 目标

同一套 worker 要能在 Claude Code、Codex、DSH、豆包、WorkBuddy 等不同 Agent 上跑。
这些平台的技能加载、子代理、图片查看、权限、工具名都不一样。做法：

- **提示词可复制**：`prompts/` 是纯 Markdown，任何聊天窗口都能粘贴；
- **状态在磁盘**：`state.json` + `roles/*.result.json`，换会话/换 Agent 能接上；
- **脚本不调用模型**：`scripts/` 只做状态、执行、截图、校验；
- **不写死工具名**：提示词说“读取文件/执行命令/查看图片/写文件”，平台自己映射。

## 能力清单

`_worker/capabilities.json`：

```json
{
  "os": "windows",
  "shell": "bash|powershell|sh|none",
  "python": "3.13",
  "file_read": true,
  "file_write": true,
  "image_view": true,
  "subagents": true,
  "gui": true,
  "web": true,
  "word_com": true,
  "libreoffice": false,
  "screenshot_backend": "pillow|powershell|gnome-screenshot|scrot|screencapture|none",
  "desktop_backend": "win32|uia|pywinauto|xdotool|applescript|none"
}
```

`env.py --write` 自动填 OS/Python/依赖/后端；`image_view`/`subagents`/`web` 由用户在平台侧确认。

## 降级

| 缺失 | 降级 |
| --- | --- |
| `image_view` | 截图验收转人工，或调用平台视觉能力 |
| `subagents` | 单会话顺序角色 |
| `gui` | 需要点击的步骤转人工操作卡 |
| `web` | 只用用户提供的材料 |
| `word_com` | LibreOffice 或仅 `.docx`；`.doc` 说明限制 |
| `python`/`shell` | 纯 Markdown 人工模式，`worker.py` 不参与 |
| 截图后端 | 人工截图 + 回传目录 |
| `scrot`/`xdotool`（Linux） | 安装后重试，或人工接管 |
| 无障碍树 | 视觉坐标兜底；仍不行人工 |

## 调用方式

### 技能目录

平台支持技能目录：把 `report-worker/` 放进去，加载 `SKILL.md`。
依赖的三个 skill 也放进去，或用 `REPORT_SKILLS_DIR` 指定。

### 只能粘贴提示词

1. 粘贴 `prompts/00_conductor.md`；
2. 初始化/状态命令如果平台能执行就执行；不能执行就手工维护 `state.json`；
3. 每个阶段粘贴对应角色提示；
4. 角色做完后，把 `result.json` 写进 `_worker/roles/`（平台不能写文件的话，让用户保存）。

### 能执行命令

直接：

```bash
python scripts/worker.py --workspace <WS> status
python scripts/worker.py --workspace <WS> next
```

平台不能执行命令时，`worker.py` 不参与；仍然按同一套验收标准人工检查。

## 路径解析

依赖的三个 skill 按顺序找：

1. `REPORT_SKILLS_DIR`；
2. `_worker/skills.json` / `.report-skills.json`；
3. 常见技能目录（`~/.claude/skills`、`~/.codex/skills`、平台配置目录等，找到就用）；
4. 与 worker 同级/上级仓库的 `../<name>/SKILL.md`；
5. 用户指定。

脚本一律用绝对路径调用；不要假设 CWD 是 skill 目录。

## 跨会话续跑

1. `worker.py status`；
2. `worker.py next`；
3. 读 `state.json`、`roles/*.result.json`、`actions.jsonl`；
4. 从当前阶段继续。

不要因为换了 Agent 就重新规划；计划已冻结就按计划走，除非用户要求变更。

## 平台差异

| 平台 | 注意 |
| --- | --- |
| Claude Code | 可直接加载技能；有子代理时优先用 |
| Codex | 按平台技能/提示词机制加载；脚本路径用绝对路径 |
| DSH / 豆包 / WorkBuddy | 不假设技能目录；优先用 `prompts/` 粘贴模式 |
| 无 Python 的聊天平台 | 纯提示词 + 用户手工执行；状态可由用户保存 |
| 无图片查看 | 截图验收转人工 |
| 无 Shell | 不能跑脚本；只能按提示词人工走 |

## 环境隔离（所有平台一致）

- Python 依赖进任务 `.venv`，不装全局；
- 环境变量只给子进程；
- 不改系统环境变量/shell profile；
- 不在宿主装系统包；
- 不关闭/杀掉宿主 Agent 的终端或进程。

详见 `environment-isolation.md`。

## 禁止

- 在提示词里写死 `Read`、`Bash`、`Skill`、`Agent`、`Task` 等平台工具名；
- 假设一定有子代理/图片查看/GUI；
- 假设某个固定技能目录存在；
- 换平台后重新开始，覆盖旧状态。
