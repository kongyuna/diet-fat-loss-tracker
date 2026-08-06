# 饮食减脂记录 Skill

一个面向普通成年人的中文饮食减脂记录 Skill。接收餐食照片或简单描述，估算热量、蛋白质和碳水，持续写入 CSV，并先给结论、再反馈当天摄入详情；支持月度体重复核以及离线 HTML 周报、月报。

## 主要能力

- 首次使用和每月月初集中收集必要资料，生成或更新摄入目标。
- 从餐食照片及可选文字估算份量和三项营养数据，保留区间、采用值和可信度。
- 每种食物一行写入 CSV，回读成功后才确认“已写入”。
- 每餐先给结论，再提供本餐合计、今日累计和一个下一餐建议；展示方式由 AI 自行选择。
- 输出“若今天此后不再进食”的单日组织能量等价，明确不等于明早秤重。
- 从同一份账本生成自包含、移动端友好的周报和月报 HTML。
- 月度体重数据充分时比较预测与实测，保守校准后续维持热量估算。

## 适用边界

面向 18 岁以上、无需疾病营养管理的普通成年人。未成年人、孕哺期、进食障碍史，以及糖尿病、肾病、肝病等需要个体化营养管理的情况，不应使用本 Skill 自动设定减脂目标，请咨询医生或注册营养师。

所有图片营养估算都存在误差。本项目是记录和趋势辅助工具，不是医疗诊断或减重效果保证。

## 目录

```text
diet-fat-loss-tracker/
├── .gitignore
├── LICENSE
├── README.md
├── SKILL.md
├── references/
│   ├── profile-and-targets.md
│   └── weight-change-model.md
├── scripts/
│   ├── generate_report.py
│   └── weight_forecast.py
└── tests/
    ├── test_generate_report.py
    └── test_weight_forecast.py
```

日常 Agent 只需加载 `SKILL.md`。建档、月初更新或解释模型时才读取 `references/`；确定性计算由脚本完成，不需要把脚本内容塞进对话上下文。

## 安装

下载或克隆仓库后，把整个 `diet-fat-loss-tracker/` 目录放到目标 Agent 可以读取的 Skill 目录或工作区中。

Codex 的个人 Skill 可放在：

```text
~/.codex/skills/diet-fat-loss-tracker/
```

其他支持 Agent Skills 或项目规则文件的工具，应让 Agent 能读取 `SKILL.md` 及其相对路径资源。不同平台的加载方式可能不同，不要只复制 `SKILL.md` 而遗漏 `references/` 和 `scripts/`。

运行环境只需要 Python 3.9 或更新版本；两个脚本均仅使用 Python 标准库，不会联网。

## 快速开始

把 `减脂档案.md` 和 `饮食记录.csv` 放在 Skill 目录的上一级工作目录，或在调用脚本时显式指定路径。首次对话可以直接说：

```text
请使用这个减脂饮食记录 Skill 帮我初始化。我会每天发送餐食照片，每月记录一次体重。
```

之后发送照片，并可补充一句：

```text
今天午餐，全部吃完；饮料无糖。
```

每次回复首先给出本餐和当天最重要的结论，以及一个下一餐动作；随后提供食物明细、本餐三项营养区间与采用值、今日累计与目标差额、写入状态和条件体重变化。Skill 不规定固定表格或进度条，AI 可根据 Trae 等当前工具的原生能力选择文字、Markdown、卡片或图表。

## 数据文件

`饮食记录.csv` 固定保存每日餐食和可选运动，不保存体重。体重、目标和月度校准保存在 `减脂档案.md`。

请勿把包含真实姓名、身体资料、照片或饮食历史的数据文件提交到公共 GitHub 仓库。公开仓库通常只需要本目录中的 Skill、参考文件、脚本、测试和 README。

## 报告与预测命令

在 `diet-fat-loss-tracker/` 的上一级目录运行：

```bash
python3 diet-fat-loss-tracker/scripts/weight_forecast.py daily 2026-08-06
python3 diet-fat-loss-tracker/scripts/weight_forecast.py month 2026-08
python3 diet-fat-loss-tracker/scripts/generate_report.py week --date 2026-08-06
python3 diet-fat-loss-tracker/scripts/generate_report.py month --date 2026-08-06
```

数据不在默认位置时，使用 `--csv`、`--profile` 和报告命令的 `--output-dir` 指定路径。预测脚本输出一行 JSON；报告脚本生成固定文件名的离线 HTML。

## 科学边界

单日结果使用 Forbes–Hall 两组分能量模型和体脂估算形成组织能量等价区间。它不会把固定 `7700 kcal/kg` 当作精确体重预测，也不会把设备显示的运动热量全部吃回。

月度校准要求相邻体重具有准确称重日期，并至少有 20 个完整饮食记录日且覆盖率达到 70%。误差平滑和单月限幅属于保守工程参数，不是临床标准。详细公式和论文来源见 [体重变化模型](references/weight-change-model.md)。

## 开发验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s diet-fat-loss-tracker/tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py diet-fat-loss-tracker
```

当前 V5 测试覆盖每日区间、额外有氧、肥胖程度差异、缺失数据、月度覆盖门槛、平滑限幅、HTML 报告及“结论优先、展示自由”的输出契约。

## 许可证

本项目采用 [MIT License](LICENSE)。复用、修改或分发时请保留版权和许可声明。

## GitHub 发布检查

- 只提交可公开的 Skill 文件，不提交个人档案、饮食 CSV、照片或生成报告。
- 检查测试全部通过，并确认仓库中没有临时文件或本地绝对路径。
- `.gitignore` 已默认排除个人账本、月度档案、报告和 Python 缓存。
