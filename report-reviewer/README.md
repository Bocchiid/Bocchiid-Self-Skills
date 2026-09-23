# report-reviewer

温州大学计算机与人工智能学院实验报告审核 Skill。

以实验要求/模板为基准，对实验报告做正确性检查、格式检查、要求对标，最终输出"要求-得分"对比表和修改建议。覆盖网络工程、编程、公选课三类实验。

## 功能

- **正确性检查（前置）**：事实性错误、逻辑矛盾、前后不一致、命令选项误用等。
- **格式检查（中间）**：字体、字号、标题层级、图表编号、标点统一。
- **要求对标**：逐条对照要求文档，标注满足/部分满足/未满足/无法核验。
- **评分输出**：生成要求-得分对比表，附问题清单和总体修改建议。
- **多轮迭代**：支持对比修改后的报告，确认旧问题是否修复。

## 目录结构

```
report-reviewer/
├── SKILL.md                          # 主指令
├── references/
│   ├── grading-rubric.md             # 默认评分标准
│   ├── domain-checks.md              # 学科领域检查规则
│   └── common-issues.md              # 常见问题清单
└── scripts/
    └── parse_docx.py                 # Word 格式信息提取脚本
```

## 安装

将整个 `report-reviewer` 文件夹复制到对应平台的 skills 目录下。

| 平台                         | 项目级路径                          | 个人级路径                                    |
| ---------------------------- | ----------------------------------- | --------------------------------------------- |
| Claude Code                  | `.claude/skills/report-reviewer/`   | `~/.claude/skills/report-reviewer/`           |
| Codex                        | `.codex/skills/report-reviewer/`    | `~/.codex/skills/report-reviewer/`            |
| GitHub Copilot               | `.github/skills/report-reviewer/`   | `~/.copilot/skills/report-reviewer/`          |
| Cursor                       | `.cursor/skills/report-reviewer/`   | `~/.cursor/skills/report-reviewer/`           |
| Windsurf                     | `.windsurf/skills/report-reviewer/` | `~/.codeium/windsurf/skills/report-reviewer/` |
| 豆包（Windows/macOS 客户端） | —                                   | `~/Doubao/skills/report-reviewer/`            |
| DSH                          | `.dsh/skills/report-reviewer/`      | `~/.dsh/skills/report-reviewer/`              |

复制完成后重启会话，Skill 即可被加载。

> 豆包的技能路径以客户端实际行为为准，未来可能调整。
> DSH 的路径基于其命名惯例，若与实际版本不符请以实际为准。

## 依赖

### 必需
无。Skill 本身是纯 Markdown 指令，不装任何东西也能运行。

### 可选（用于完整格式检查）
格式检查（字体、字号、标题层级）依赖 Python 和 `python-docx`：

```
pip install python-docx
```

**不装会怎样**：格式检查降级为基于文本内容推断层级，无法验证字体和字号。Skill 会在审核报告开头标注"格式检查受限"。

**装不上怎么办**：换国内镜像源：

```bash
pip install python-docx -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 使用

在会话中提交实验报告（.docx）和对应的实验要求/模板（.docx 或 .pdf），然后提出审核需求，例如：

> 帮我审核这份实验报告，对照模板和要求检查。

Skill 会自动：

1. 静默探测环境，判断能否读取 Word 格式信息。
2. 若缺少 `python-docx`，询问是否安装（仅问一次）。
3. 按正确性 → 格式 → 要求对标 → 评分的顺序审核。
4. 输出要求-得分对比表、问题清单和修改建议。

## 输出示例

### 审核结论

有条件通过。

### 要求-得分对比表

| 要求条目        | 满分 | 得分 | 依据                       | 修改建议          |
| :-------------- | :--- | :--- | :------------------------- | :---------------- |
| 一、实验目的    | 5    | 5    | 完整照抄模板               | —                 |
| 五-1 配置项解释 | 10   | 8    | 解释了8项，其中2项描述有误 | 修正 `-l` 为 `-I` |

### 问题清单

- 【正确性错误】第5题：`-ladd` 应为 `-Iadd`，且解释与命令不符。
- 【格式问题】"六：思考题"应为"六、思考题"，标点与前面章节不统一。
- 【要求未满足】模板要求"含实验总结"，报告缺少总结段落。

## 适用与不适用

**适用**

- 温州大学计算机与人工智能学院的实验报告。
- 网络工程、编程、公选课三类实验。
- 有明确实验要求/模板作为基准的审核场景。

**不适用**

- 没有基准材料的自由写作。
- 需要查重、查抄袭的场景。
- 需要直接替学生重写报告的场景。

## 自定义

- **调整评分权重**：修改 `references/grading-rubric.md`。
- **增删学科规则**：修改 `references/domain-checks.md`。
- **补充常见问题**：修改 `references/common-issues.md`。
- **调整审核流程**：修改 `SKILL.md`。

## 许可

MIT，详见 [LICENSE](../LICENSE)。