# 减脂饮食与训练记录 Skill

一个面向普通成年人的中文减脂与训练组合 Skill。它保留原有餐食估算、每日摄入进度、体重趋势和 HTML 周/月报，同时新增力量/有氧落账、解剖化训练部位图、恢复复查窗口、滚动训练计划和月度联合复核。

当前正式版本：`v2.1.0`。

## 主要能力

- 首次使用和每月月初通过选择组件或成组问题收集必要资料，生成或更新摄入目标。
- 对照 Schofield、Mifflin、Liu 和 Xue1 四种基础代谢公式；以 Schofield 为 18～59 岁初始中心值，并用中国人群研究、目标期限和真实体重趋势约束结果。
- 从餐食照片、可选文字或本地食物库估算份量、热量、蛋白质、碳水和脂肪，保留区间、采用值和可信度。
- 每种食物一行写入 CSV，回读成功后才确认“已写入”。
- 普通记录只展示本餐四项采用值、热量/蛋白质/碳水今日进度、一个建议和写入状态；详细食物表、误差分析和体重预测仅在用户主动分析或日总结时展开。
- 脂肪只作为餐食估算和账本数据，不建立每日/月度脂肪目标、进度条或报告图表。
- 从同一份账本生成自包含、移动端友好的周报和月报 HTML。
- 月度体重数据充分时比较预测与实测，保守校准后续维持热量估算。
- 初次建立训练目标、经验、器械、时长、频率范围和限制；月初与体重一起询问是否变化。
- 每个动作写入独立训练账本，用唯一训练 ID 幂等同步一条饮食运动摘要。
- 根据主要/次要部位、组数或时长、RIR/RPE 和主观感受输出宽恢复窗口。
- 生成带正面/背面和直接肌群标注的确定性 HTML/矢量部位图，同样输入得到同样结果，不反复消耗图片生成 token。
- 根据实际可用时间执行滚动 A/B 队列，不绑定固定星期或每周次数。

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
├── assets/
│   ├── food-data/
│   │   ├── SOURCE.md
│   │   └── tw_food_macros.csv
│   └── muscle-map-anatomical.svg
├── references/
│   ├── profile-and-targets.md
│   ├── training-and-recovery.md
│   └── weight-change-model.md
├── scripts/
│   ├── generate_report.py
│   ├── food_lookup.py
│   ├── target_planner.py
│   ├── training_tracker.py
│   └── weight_forecast.py
└── tests/
    ├── test_food_lookup.py
    ├── test_generate_report.py
    ├── test_target_planner.py
    ├── test_training_tracker.py
    └── test_weight_forecast.py
```

日常 Agent 只需加载 `SKILL.md`。普通餐食不会读取训练规则或训练历史；用户提到训练、恢复、可用时间或计划时才加载训练 reference。确定性计算由脚本完成，不需要把脚本内容塞进对话上下文。

## 安装

下载或克隆仓库后，把整个 `diet-fat-loss-tracker/` 目录放到目标 Agent 可以读取的 Skill 目录或工作区中。

Codex 的个人 Skill 可放在：

```text
~/.codex/skills/diet-fat-loss-tracker/
```

其他支持 Agent Skills 或项目规则文件的工具，应让 Agent 能读取 `SKILL.md` 及其相对路径资源。不同平台的加载方式可能不同，不要只复制 `SKILL.md` 而遗漏 `references/` 和 `scripts/`。

运行环境只需要 Python 3.9 或更新版本；脚本仅使用 Python 标准库。日常记录和查询默认离线；只有维护者显式重建食物库时才会下载已声明来源的数据。

## 快速开始

把 `减脂档案.md` 和 `饮食记录.csv` 放在 Skill 目录的上一级工作目录，或在调用脚本时显式指定路径。首次对话可以直接说：

```text
请使用这个减脂与训练 Skill 帮我初始化。我会发送餐食和训练记录，每月记录一次体重；训练时间不固定。
```

之后发送照片，并可补充一句：

```text
今天午餐，全部吃完；饮料无糖。
```

普通餐食反馈按“本餐采用值 → 今日进度条 → 一个建议 → 写入状态”排列。需要复盘时再说“分析这餐”或“总结今天”，Skill 才展开详细食物表、估算区间、可信度、4/9/4 热量复核和条件性体重变化。具体卡片、配色和进度条样式由 AI 决定；当前工具适合时可以使用简洁、自包含的 HTML、CSS 或 JS。

训练时可以直接说：

```text
今天深蹲 3×8×60kg、卧推 3×8×40kg、划船 3×10×35kg，RIR 大约 2，整体感觉刚好。
```

临时有时间时说“今天能训练 40 分钟”。Skill 会读取滚动队列和当前恢复状态选择下一节；本周只练一次或临时练多次都不会重置计划。

## 数据文件

`饮食记录.csv` 使用 22 列保存每日餐食和运动摘要，其中脂肪下限、上限和采用值位于采用碳水之后；旧记录迁移后这三列留空，不反推历史脂肪。`训练记录.csv` 一行一个动作；`减脂档案.md` 是体重、营养目标和训练配置的唯一档案。训练明细与饮食摘要通过 `[training:训练ID]` 关联，重试不会重复新增。

请勿把包含真实姓名、身体资料、照片或饮食历史的数据文件提交到公共 GitHub 仓库。公开仓库通常只需要本目录中的 Skill、参考文件、脚本、测试和 README。

## 报告与预测命令

在 `diet-fat-loss-tracker/` 的上一级目录运行：

```bash
python3 diet-fat-loss-tracker/scripts/target_planner.py --help
python3 diet-fat-loss-tracker/scripts/food_lookup.py lookup 白饭
python3 diet-fat-loss-tracker/scripts/weight_forecast.py migrate --csv 饮食记录.csv --dry-run
python3 diet-fat-loss-tracker/scripts/weight_forecast.py daily 2026-08-06
python3 diet-fat-loss-tracker/scripts/weight_forecast.py month 2026-08
python3 diet-fat-loss-tracker/scripts/generate_report.py week --date 2026-08-06
python3 diet-fat-loss-tracker/scripts/generate_report.py month --date 2026-08-06
python3 diet-fat-loss-tracker/scripts/training_tracker.py --help
```

确认迁移预览的行数和状态后，移除 `--dry-run` 执行。迁移会原子替换账本，备份仅放在系统临时目录；重复执行不会再次插列。

随包食物库来自台湾 FDA 政府开放数据，压缩为 2181 种食物的四项宏量营养数据。它适合离线初筛，但地区、品牌、烹调方式和简繁名称都可能不一致；没有唯一匹配时脚本只返回候选，不会自行选定。来源、许可和校验值见 [食物数据说明](assets/food-data/SOURCE.md)。

训练脚本提供：

```bash
# 首次训练配置
python3 diet-fat-loss-tracker/scripts/training_tracker.py configure \
  --goal "减脂保肌" --experience "初级" --equipment "健身房" \
  --minutes "30～60分钟" --frequency "不固定，0～3次/周"

# 查看下一节；日期时间使用本地时间
python3 diet-fat-loss-tracker/scripts/training_tracker.py plan \
  --available-minutes 40 --as-of 2026-08-09T18:00

# 查看部位恢复行动分档
python3 diet-fat-loss-tracker/scripts/training_tracker.py status \
  --as-of 2026-08-09T18:00

# 将实际训练与原计划比较；--plan 可直接传 plan 命令的一行 JSON
python3 diet-fat-loss-tracker/scripts/training_tracker.py evaluate \
  --session-id 20260809-example \
  --plan '{"exercises":[{"exercise":"深蹲","sets":"3","reps":"6～10","target_rir":"2～4"}]}'

# 生成临时训练部位 HTML；默认覆盖系统临时目录，不污染当前文件夹
python3 diet-fat-loss-tracker/scripts/training_tracker.py render \
  --start 2026-08-04 --end 2026-08-10

# 只有明确需要长期保存时才指定输出路径
python3 diet-fat-loss-tracker/scripts/training_tracker.py render \
  --start 2026-08-04 --end 2026-08-10 --output 训练部位-本周.html
```

数据不在默认位置时，使用各命令的 `--help` 查看 `--training-csv`、`--diet-csv`、`--profile` 和 `--output`。预测及训练脚本输出一行 JSON；报告脚本生成固定文件名的离线 HTML。

## 科学边界

热量目标不是由单一公式直接决定：18～59 岁先比较四种公式，公式离散度超过 10% 时降低可信度；60 岁以上不自动承诺激进期限。公式只给初始估计，最终应结合 2～4 周体重趋势保守校准。详细规则和中国人群证据见 [档案与目标规则](references/profile-and-targets.md)。

单日结果使用 Forbes–Hall 两组分能量模型和体脂估算形成组织能量等价区间。它不会把固定 `7700 kcal/kg` 当作精确体重预测，也不会把设备显示的运动热量全部吃回。

月度校准要求相邻体重具有准确称重日期，并至少有 20 个完整饮食记录日且覆盖率达到 70%。误差平滑和单月限幅属于保守工程参数，不是临床标准。详细公式和论文来源见 [体重变化模型](references/weight-change-model.md)。

恢复模块输出的是“下一次重训复查窗口”和行动分档，不是肌肉组织恢复完成时间。力竭、陌生动作、睡眠、能量缺口和个体差异都可能改变恢复；疼痛或明显动作异常会停止自动计划。详细规则见 [训练、恢复与滚动计划](references/training-and-recovery.md)。

## 开发验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s diet-fat-loss-tracker/tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py diet-fat-loss-tracker
```

当前 `v2.1.0` 共 40 项测试，覆盖原有饮食、预测、HTML 报告和训练合同，并覆盖四公式目标规划、期限可行性、食物库许可与唯一匹配、19→22 列无损迁移及幂等性，以及脂肪不扩张到每日/月度目标和报告。

## 许可证

本项目采用 [MIT License](LICENSE)。复用、修改或分发时请保留版权和许可声明。

## GitHub 发布检查

- 只提交可公开的 Skill 文件，不提交个人档案、饮食 CSV、照片或生成报告。
- 检查测试全部通过，并确认仓库中没有临时文件或本地绝对路径。
- `.gitignore` 已默认排除个人账本、月度档案、报告和 Python 缓存。
