# Wireshark 操作提示

## 窗口

- Windows/桌面版标题通常含 `The Wireshark Network Analyzer`；
- Linux guest 标题可能含 `Wireshark`；
- 先 `list-windows` 确认真实标题。

## 常用动作

| 目标 | 动作 | 验证 |
| --- | --- | --- |
| 选接口 | 点接口列表/`Capture` 页，选 `any` 或指定网卡 | 出现 `Capturing on ...` |
| 开始抓包 | 点蓝色鲨鱼鳍/`Start` | 状态栏显示抓包中，包列表增长 |
| 显示过滤器 | 点过滤器输入框，输入 `openflow_v1` / `openflow_v4`，回车 | 包列表只剩 OpenFlow |
| 选报文 | 点包列表中 `OFPT_PACKET_IN` / `OFPT_FLOW_MOD` / `OFPT_PACKET_OUT` | 详情树展开 |
| 展开字段 | 点树节点 `OpenFlow` / `Version` / `Type` / `Buffer ID` | 详情出现对应字段 |
| 保存 pcap | `Ctrl+Shift+S` 或 `File → Save As` | 文件存在、大小 > 0 |

## 控件定位

```bash
python scripts/desktop.py uia --action list --window "The Wireshark Network Analyzer"
```

- 报文列表项的名称通常是协议/信息列文本；用子串匹配。
- 详情树的字段名可能带值，例如 `Version: 1.0`；`expect` 用 `Buffer ID` 这类稳定子串。
- 控件树太深/为空时，用坐标（必须先截图确认目标，再 `--confirm`）。

## 证据要点

- Packet-In：Version、Type、Length、Buffer ID、Total length、In port、Reason；
- Flow-Mod：match（wildcards/in_port/eth_src/eth_dst）、cookie、actions；
- 握手：HELLO、FEATURES_REQUEST/REPLY、MULTIPART、FLOW_MOD、PORT_STATUS；
- 保存 pcap 作为原始证据，截图作为报告插图。

## 验证失败

| 现象 | 处理 |
| --- | --- |
| 过滤器没生效 | 确认焦点在过滤器框；按回车；看过滤器变绿/红 |
| 包列表为空 | 接口选错/没流量；先 `ping` 或 `pingall` |
| 详情树没有字段 | 选错包/没展开；重新选 `OFPT_*` |
| 截图裁掉字段 | 拉大窗口/滚动到字段，重新截 |
| 保存对话框挡住 | 先保存，再截结果图 |
