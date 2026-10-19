# 环境隔离：不破坏用户原来的环境

这是硬规则。worker 可以为了实验装工具、设变量，但**只能在自己的任务目录/子进程里生效**，
不能改用户的全局 PATH、全局 Python、系统环境变量、shell 配置或系统包。

## Python：任务级 venv

默认在任务目录建 `.venv`：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" venv
```

带依赖时先生成计划、用户确认后安装：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" venv \
  --packages pywinauto --packages mss --confirm
```

- venv 固定在 `<WS>/.venv`，不装到全局 site-packages；
- `actions.py run` 会自动把 `<WS>/.venv/Scripts`（Windows）或 `<WS>/.venv/bin`（POSIX）
  放到**子进程** PATH 前面，并设置 `VIRTUAL_ENV`；
- `capture.py` / `desktop.py` / `verify.py` 如果发现全局解释器缺 Pillow/pywin32/python-docx，
  会自动用 `<WS>/.venv` 的解释器重跑自己（`_venv.py`），不会全局装包；
- 不会执行 `pip install --user`，不会改系统 Python；
- 不想用 venv 时显式 `--no-venv`，但要说明原因。

验证：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" env
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" run \
  --command "python -c \"import sys; print(sys.prefix)\""
```

`sys.prefix` 应该指向 `<WS>/.venv`，不是全局 Python。

## 环境变量：只给子进程

用：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" run \
  --env-var "MY_FLAG=1" --command "python experiment.py"
```

或 `.env` 文件：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" run \
  --env-file "_worker/experiment.env" --command "python experiment.py"
```

- 变量只进入这一条命令的子进程；
- 不执行 `setx`、`[Environment]::SetEnvironmentVariable`、`export` 到用户 shell、
  不写 `.bashrc`/`.zshrc`/PowerShell `$PROFILE`；
- 不在日志里记录密码/token；`actions.py` 会对命令和输出里的常见敏感键做脱敏，
  但**不要把密码直接写进命令行**，优先用 `--env-file` 且不要提交该文件；
- WSL/SSH 场景用 `export KEY=...; command` 前缀，只在远端那一条命令里生效。

## 系统包 / 宿主软件

- **不在 Windows 宿主上** `winget install` / `choco install` / 改注册表；
- WSL/VM 里需要 `apt install` 时，先列清单，用户确认后由用户在 guest 内执行；
- 能用便携版/解压版就不装系统包；
- 不装内核模块、驱动、服务；不关系统安全软件。

## Node / 其他

- Node 依赖装到项目 `node_modules`，不用 `npm install -g`；
- 能用 `npx` 就用 `npx`；
- Java/其他工具放 `<WS>/.tools/` 或用户指定的目录，改 PATH 只改子进程。

## 清理

- `.venv`、`.tools` 都在任务目录内，交付时可保留（便于复现）或由用户决定删除；
- **不删除任务目录之外的东西**；
- 不删用户原有的包/缓存/配置。

## 进程与窗口安全

**绝对不要关闭/杀掉宿主 Agent 的终端、IDE、Claude Code/Codex/DSH 等进程。**

- 不执行 `taskkill /IM powershell.exe`、`Stop-Process -Name ...`、`pkill python` 这类宽范围命令；
  `actions.py` 会把它们判为 hard deny；
- 只清理 worker 自己打开、且记录了 PID/窗口标题的测试窗口；
- 不确定某个窗口/进程是不是宿主的，**留着不动，问用户**；
- 清理动作走确认闸门，记录到 `actions.jsonl`；
- 报告/实验结束不需要“关掉所有窗口”；关不关由用户决定。

## 隔离检查清单

- [ ] Python 命令的 `sys.prefix` 指向任务 `.venv`
- [ ] 没有全局 `pip install`
- [ ] 没有 `setx` / 改 profile / 改系统环境变量
- [ ] 没有在宿主装系统包/驱动/服务
- [ ] 没有杀宿主进程或关宿主窗口
- [ ] 所有临时文件在任务目录或 `_worker/`
- [ ] 用户原来的环境可以用一条命令验证没变
