# GUI 定位与动作验证

## 目标

让 worker 像人一样看屏幕、找目标、操作、确认结果。**不是**“点一下试试”，而是
“我知道现在是什么窗口、我要点哪个控件、点完应该看到什么”。

## 定位顺序

1. **控件树**（最稳）
   - Windows：UIA（`uia.ps1`）；
   - Linux：AT-SPI / `pyatspi`（v0.2）；
   - macOS：Accessibility / AppleScript。
   - 按窗口标题 + 控件名/AutomationId 查找；找不到再做子串匹配。
2. **键盘**
   - 菜单/快捷键/搜索框通常比坐标稳；
   - 例如 Wireshark 的显示过滤器、MiniEdit 的导出菜单。
3. **归一化坐标**（兜底）
   - 从截图给出 `x_pct`/`y_pct`（0~1），`desktop.py` 换算成窗口物理像素；
   - 必须 `--confirm`，并且带 `expect`。
4. **人工接管**
   - 控件/坐标都不稳，或属于不可逆操作。

## 动作文件

```json
{
  "id": "A012",
  "step": "S8",
  "app": "Wireshark",
  "window": "The Wireshark Network Analyzer",
  "before": "Pictures/_raw/A011.png",
  "target": {"kind": "uia", "name": "OFPT_PACKET_IN"},
  "action": "click",
  "expect": {"type": "uia_text", "value": "Buffer ID", "timeout_s": 10},
  "after": "Pictures/S8_PacketIn.png",
  "timeout_s": 10,
  "settle_s": 0.5
}
```

坐标：

```json
{
  "target": {"kind": "point", "x_pct": 0.42, "y_pct": 0.31,
             "description": "Start 按钮"},
  "expect": {"type": "uia_text", "value": "Capturing on any"}
}
```

## 常见应用

### Wireshark

- 窗口标题：`The Wireshark Network Analyzer`（不同版本可能不同，先 `list-windows`）。
- 显示过滤器：优先点过滤器输入框 + `type_text` + `enter`；不要盲点菜单。
- 报文列表：控件名通常是 `OFPT_PACKET_IN`、`OFPT_FLOW_MOD` 等；点击后详情树出现
  `Version`、`Type`、`Length`、`Buffer ID`、`Reason`。
- 验证：`uia_text` 找 `Buffer ID`；如果控件树不暴露文本，用 `screenshot_changed` +
  截图验收人工确认。
- 保存 pcap：用 `File → Save As` 或 `Ctrl+Shift+S`；文件落盘用 `file_exists` 验证。

### MiniEdit

- 窗口标题通常含 `MiniEdit`。
- 拖拽节点/连线不适合坐标盲点；优先用菜单/属性对话框 + 键盘。
- 导出脚本：`File → Export Level 2 Script`，验证文件存在 + 关键行（`RemoteController`、
  `tcp`、`6653`）。
- 拓扑截图：窗口截图，保留节点名/链路。

### 终端

- 窗口标题：`Windows Terminal`、`PowerShell`、`Ubuntu` 等。
- 用 `terminal-run`，不要手写 `SendKeys`。
- 命令输出必须同屏：命令 + 关键输出 + 提示符。
- WSL 日志路径用 `/mnt/...`。

### 浏览器

- v0.1 不做登录/提交；只读页面截图；
- 优先 Playwright（v0.2）；否则人工。

## 失败模式

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `wrong_window` | 前台窗口不对/标题变了 | `list-windows` 重新找；不要硬点 |
| `not_found` | 控件名不对/树太深 | `uia list` 看真实名字；换键盘/坐标 |
| `no_change` | 点错/被遮挡/还在加载 | 等一会重试；截图看状态；换目标 |
| 坐标偏移 | DPI/多屏/窗口移动 | 用窗口相对坐标；重新截图；设 DPI 感知 |
| 截图黑屏 | 窗口最小化/独占全屏 | 还原窗口；用全屏截图 |
| 控件树为空 | 应用自绘/Java/Qt 未开无障碍 | 坐标/键盘兜底；仍不行人工 |

## 禁止

- 没有目标描述、没有预期变化的点击；
- 连续盲点同一个坐标；
- 把“点了但没变”记成成功；
- 用 P 图/合成图补证据。
