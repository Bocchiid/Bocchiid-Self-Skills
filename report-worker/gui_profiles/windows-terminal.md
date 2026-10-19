# Windows Terminal / PowerShell 操作提示

## 找窗口

```bash
python scripts/desktop.py list-windows
```

标题通常含 `Windows Terminal`、`PowerShell`、`Ubuntu`、`命令提示符`。
标题可能被标签页改成项目名，先看实际标题。

## 聚焦

```bash
python scripts/desktop.py focus --title "Windows Terminal"
```

## 跑一条命令并截图

```bash
python scripts/desktop.py terminal-run \
  --window "Windows Terminal" \
  --shell powershell \
  --command "ping 127.0.0.1 -n 3" \
  --log "C:/path/to/task/_worker/logs/ping.log" \
  --timeout 60
```

- `terminal-run` 会：聚焦 → 粘贴命令 → 回车 → 轮询日志结束标记 → 截窗口。
- 命令必须是单行；多行用 `;` 连接。
- 日志路径必须是终端能看到的路径；WSL 用 `/mnt/c/...`。
- 截图默认保存到 `_worker/actions/terminal_*.png`；需要作为证据时再 `capture.py add`。

## 验证

- 日志里出现结束标记和退出码；
- 截图同屏包含命令、关键输出、提示符；
- 如果终端没有变化：确认焦点在输入行、没有被正在运行的进程占用。

## 失败

- 窗口找不到：让用户打开终端，或 `list-windows` 看真实标题；
- 命令没执行：先 `focus` 再 `type_text` + `keys enter`；
- 输出被截断：滚到命令开头/结尾，或分两次截图；
- 需要 TTY 交互（密码/`less`/`ping` 不停）：改用非交互参数或人工接管。
