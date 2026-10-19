# 跨 Agent / 独立使用

## 目标

同一套 worker 要能在 Claude Code、Codex、DSH、豆包、WorkBuddy 等不同 Agent 上跑。
做法：

- `prompts/` 是纯 Markdown，可复制到任意聊天窗口；
- 状态在磁盘：`_worker/state.json` + `roles/*.result.json`；
- 脚本不调用模型，只做状态/执行/截图/校验；
- 提示词不写死平台工具名，说“读取文件/执行命令/查看图片/写文件”。

## 调用方式

| 平台能力 | 用法 |
| --- | --- |
| 能加载技能目录 | 加载 `SKILL.md` |
| 只能粘贴提示词 | 粘贴 `prompts/00_conductor.md`，按阶段再粘对应角色提示 |
| 能执行命令 | 直接跑 `python scripts/worker.py ...` |
| 不能执行命令 | 纯 Markdown 人工模式 |
| 有子代理 | 每个角色交给子代理，主会话只收 `result.json` |
| 无子代理 | 单会话顺序执行，角色之间靠 `result.json`/`state.json` 隔离 |

## 依赖 skill 路径

按顺序找：

1. `REPORT_SKILLS_DIR`；
2. `_worker/skills.json` / `.report-skills.json`；
3. 常见技能目录（找到就用，不假设只有某一家）；
4. 与 worker 同级的 `../report-planner` 等；
5. 用户指定。

缺依赖先问安装/复制，不硬跑。

## 能力降级

| 缺失 | 降级 |
| --- | --- |
| 图片查看 | 截图验收交用户/平台视觉 |
| 子代理 | 单会话顺序 |
| GUI | 人工操作卡/CLI |
| Web | 只用用户材料 |
| Word COM | LibreOffice/`.docx`；`.doc` 说明限制 |
| Python/shell | 纯 Markdown 人工模式 |
| 截图后端 | 人工截图 + 回传 |
| WSL/Linux | 先问用户；没有就换方案或人工 |

## 独立使用

三个依赖 skill 都可以单独使用：

- 只要规划 → `report-planner`；
- 只要写报告 → `report-writer`；
- 只要审核 → `report-reviewer`；
- 需要串起来/闭环 → `report-worker`。

worker 不修改、不内嵌它们的规则；它们更新后，worker 按路径读取最新版。

## 禁止

- 写死某台机器/某个用户的路径；
- 假设一定有子代理/图片查看/GUI/Python；
- 缺依赖时硬跑；
- 换平台后重新开始，覆盖旧状态。
