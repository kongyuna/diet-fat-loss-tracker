# 体重变化模型

仅在解释模型、修改公式或排查预测时读取；普通餐食记录直接运行脚本，不加载本文件。

## 输出边界

- 每餐输出的是“若今天此后不再进食”的单日组织能量等价，不是明早体重。
- 单日体重可被水分、糖原、盐分和胃内容物淹没，因此固定标记低可信。
- 不用“热量目标－摄入”计算；能量差必须来自校准后的维持热量、当天摄入和明确额外有氧。

## 可复算模型

1. 未提供体脂时，用成人 Deurenberg 公式估算：`BF%=1.20×BMI+0.23×年龄−10.8×性别−5.4`，男性=1、女性=0；采用论文报告的 4.1 个百分点标准估计误差形成区间。
2. Forbes–Hall 两组分模型使用脂肪组织 9400 kcal/kg、去脂组织 1800 kcal/kg。能量分配比例随估算脂肪量变化，因此脂肪量越高，同样热量差对应的体重变化越小。
3. 单日采用摄入区间、体脂估算区间和有效维持热量生成范围；明确额外有氧只按既有 100/200/300 kcal 保守额度进入消耗，不读取设备热量。
4. 月度预测按相邻称重日期模拟；维持热量随模拟体重按约 23.9 kcal/kg/日变化。缺失日只有在完整记录不少于 20 天且覆盖率达到 70% 时，才用完整日均值外推并校准。
5. 月度校准只吸收推算误差的 25%，单月限制 ±100 kcal/日。这是抑制单点体重噪声的工程保护参数，不是论文给出的临床阈值。

## 依据

- Hall 等，成人体重变化动态模型与代谢适应：https://pmc.ncbi.nlm.nih.gov/articles/PMC3880593/
- Hall 模型方程附录（NIDDK）：https://www.niddk.nih.gov/-/media/Files/BWP/Hall_Lancet_Web_Appendix.pdf
- 两组分能量平衡、9400/1800 kcal/kg 与 Forbes 分配：https://pmc.ncbi.nlm.nih.gov/articles/PMC3111923/
- Deurenberg 成人体脂估算及 4.1% 标准估计误差：https://pubmed.ncbi.nlm.nih.gov/2043597/
- NIDDK Body Weight Planner 研究说明：https://www.niddk.nih.gov/research-funding/at-niddk/labs-branches/laboratory-biological-modeling/integrative-physiology-section/research/body-weight-planner

固定 7700 kcal/kg 规则不能描述长期代谢适应，也不得包装为精确体重预测。
