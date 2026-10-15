# Bocchiid-Self-Skills

个人维护的 Agent Skills 合集。

每个 Skill 独立放在一个子目录中，可单独复制到各平台的 skills 目录下使用。

## 包含的 Skills

| Skill                               | 说明                                                         |
| ----------------------------------- | ------------------------------------------------------------ |
| [report-writer](report-writer/)     | 按模板撰写 Word 报告（实验报告为主场景）：插入而非覆盖、图表题注与交叉引用、页面利用率调优。 |
| [report-reviewer](report-reviewer/) | 温州大学计算机与人工智能学院实验报告审核，覆盖网络工程、编程、公选课三类实验。 |

`report-writer` 与 `report-reviewer` 配对：**一个写、一个审**。写完用 reviewer 自审一遍。

后续会按需添加更多 Skill。

## 目录结构

```
Bocchiid-Self-Skills/
├── README.md
├── LICENSE
├── .gitignore
├── report-writer/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
└── report-reviewer/
    ├── SKILL.md
    ├── references/
    └── scripts/
```

每个 Skill 子目录自包含，安装时复制整个子目录即可。

## 安装

把需要的 Skill 子目录复制到对应平台的 skills 目录下。以 Claude Code 为例：

```text
~/.claude/skills/report-reviewer/
```

其他平台的路径见各 Skill 子目录内的说明。

## 添加新 Skill

在仓库根目录新建子目录，放入 `SKILL.md` 及配套文件，然后在上面表格中加一行。

## 许可

MIT，详见 [LICENSE](LICENSE)。