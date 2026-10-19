# MiniEdit 操作提示

MiniEdit 是 Mininet 自带的 Tk GUI，常用于拖拓扑、配 IP、导出脚本。

## 启动

```bash
sudo python ./mininet/examples/miniedit.py
```

- 需要 Linux 图形桌面（VM 或 WSLg）；
- 需要 root/sudo；在 `assist` 模式下逐条确认；
- 窗口标题通常含 `MiniEdit`。

## 常用动作

| 目标 | 动作 | 验证 |
| --- | --- | --- |
| 放控制器 | 左侧 Controller 图标 → 点击画布 | 出现 `c0` |
| 放交换机 | Switch 图标 → 画布 | 出现 `s1`、`s2` |
| 放主机 | Host 图标 → 画布 | 出现 `h1`–`h4` |
| 连线 | Link 图标 → 依次点两个节点 | 出现链路 |
| 配 IP | 右键主机 → Properties → IP | 主机旁/属性显示 IP |
| 配交换机 | 右键交换机 → Properties → 控制器/端口 | 属性正确 |
| Preferences | `Edit → Preferences` | IP Base / OVS / OpenFlow 版本 |
| 导出脚本 | `File → Export Level 2 Script` | 生成 `lab_3.py` |

## 定位

- MiniEdit 是 Tk 应用，UIA/AT-SPI 可能拿不到控件；优先用菜单/快捷键，坐标兜底。
- 坐标点击必须 `--confirm`，并先截图确认画布位置。
- 拖拽不是点击：`desktop.py` 目前没有拖拽动作；需要拖拽时转人工，或用菜单/脚本。

## 证据

- 拓扑全景截图（节点名、链路、控制器）；
- 主机 IP 配置截图（4 台可合成一张或分 4 张）；
- Preferences 截图（IP Base、OVS Kernel Mode、OpenFlow 1.0/1.3）；
- 导出脚本截图（路径 + `RemoteController`/`tcp`/`6653` 关键行）。

## 失败

- 窗口找不到：确认 `DISPLAY`/桌面会话；WSLg 可能需要等几秒；
- 画布点不中：先截全屏，确认画布区域，再用归一化坐标；
- 节点重叠：先移动/删除，再重放；
- 导出菜单灰色：确认拓扑有控制器/交换机，或先保存。
