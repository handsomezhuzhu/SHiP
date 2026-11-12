# 小报告：为什么单核 + SRRIP 的 MPPPB 只有 +3.76%

对象：Matrix-1（8 条 SPEC2017 trace，50 M warmup + 150 M 测量，单核 2 MB LLC）。
结果：MPPPB **+3.76% IPC / −5.02% MPKI**（相对 LRU），SHiP-PC +4.30% / −3.69%。
论文单核：**+9.0%**（MDPP 底座、SPEC2006、99 segments、stream prefetcher）。

## 结论先说

**不是 MPPPB 本身的上限，也不是“跑错了”**；第一次跑的是一个
**“MPPPB 预测器 + 4 级 SRRIP 底座 + 猜的 τ/π + 简化训练 + 近似 bypass”**
的组合，和论文的“MPPPB + 16 位置 MDPP + 作者参数 + 真 bypass”不是同一个策略。
差距可以逐项解释，最大头是底座和参数/训练语义。

## 差距分解

| # | 差异 | 论文/作者代码 | 我们 Matrix-1 | 预估影响 |
|---|---|---|---|---|
| 1 | **底座** | static MDPP：16 个位置、树状 PLRU、`vecmdpp` 最小扰动提升 | SRRIP：4 个 RRPV 位置，π1=π2=3 无法区分 | **最大，约 +2–4 个百分点** |
| 2 | **τ/π** | config 1：promotion 82、bypass 56/256、placement −15→0 / 35→12 / 44→15 | 猜的 c 组：250/150/75/0/100，π=3/3/2 | +1–2 |
| 3 | **训练语义** | 权重初值 1；`prediction = conf ≥ 128`；deadzone θ=109/θ2=135 | 初值 0；`conf>0/<0`；无 deadzone | +1–2 |
| 4 | **特征集** | config 1 用 `single_1` ≈ Table 1(a) | Table 1(b) | ±1，方向未知 |
| 5 | **bypass** | 真正不分配（返回 `LLC_WAYS`） | 插入 RRPV=3 + 优先逐出，块仍占 LLC | +1–3（xalan 58% fills 被 bypass，近似误差大） |
| 6 | **workload/预取** | SPEC2006、99 segments、stream prefetcher | SPEC2017、8 条、无预取 | ±2，方向未知 |
| 7 | **SHiP 对照** | 论文主对比是 Hawkeye/Perceptron，不含 SHiP | SHiP +4.30% 略高于 MPPPB | 说明我们的 MPPPB 没把多视角优势发挥出来，指向 1–4 |

> 预估影响是定性的：各项不独立，不能简单相加；但 9.0 − 3.76 = 5.24
> 个百分点的量级，用“底座 + 参数/训练 + bypass”可以覆盖大部分。

## 为什么“底座”影响这么大

1. **位置粒度**：MDPP 有 16 个位置，π1/π2/π3 可以落在不同位置；
   4 级 SRRIP 里 π1 和 π2 都只能是 3，预测器的分档信息被压掉。
2. **提升策略**：MDPP 用 `vecmdpp` 做“最小扰动”提升，不是所有命中都到 MRU；
   SRRIP 的命中提升（`conf < τ4 → 0`）扰动更大，容易把刚预测为 live 的块
   推到 MRU，反而挤掉其他块。
3. **受害者选择**：MDPP 是树状 PLRU，SRRIP 是 max-RRPV + aging；
   同样的预测置信度，两者的实际放置/逐出效果不同。
4. **参数不可移植**：作者的 τ/π 是在 MDPP 上搜的；
   我们把它们换成 4 级 RRIP 上猜的 c 组，等于换了一个策略。

## 为什么“训练语义”也重要

作者代码不是“预测错才训练”这么简单：

- 权重初值 **1**（不是 0），初始 `conf=16`；
- `prediction = conf >= 128`（单核），不是 `conf >= 0`；
- 只在预测错，或置信度落在 deadzone（`−135 < conf < 109`）时训练；
- dead 只训练 `assoc == pos` 的特征，live 只训练 `assoc > pos` 的特征。

我们 Matrix-1 用 `conf>0/<0` + 初值 0，预测器很早饱和/偏向一侧，
和作者的训练动态不同。这会让同一套 τ/π 在我们这里产生不同的
bypass/placement 比例，进一步放大差距。

## 为什么“bypass 近似”不能忽略

作者 `Get_Sampler_Victim` 在预测 dead 时直接返回 `LLC_WAYS`，
即 **不分配**；我们为了不改 ChampSim fill 路径，插入 RRPV=3 并标记
优先逐出。块仍然占一个 way，下一次 miss 才被逐出；在 xalan 上
bypass 占 58% fills，这个近似会明显低估收益，也可能扰动其他块的
放置。真正的 bypass 需要 core 里加“跳过分配”的钩子。

## 和 SHiP 的关系

SHiP-PC +4.30% IPC 略高于 MPPPB +3.76%，但 MPPPB 的 MPKI 更低
（0.9498 vs 0.9631）。这说明：

- SHiP 的 PC 签名在 soplex/xalan 上很强；
- 我们的 MPPPB 还没有把“多视角”的准确率优势转化为 IPC；
- 在底座/训练/参数对齐之前，**不能用这组结果判断 MPPPB 不如 SHiP**。

## 下一步怎么验证这个解释

1. **单核 MDPP + 作者 config 1 参数**（当前正在做）：
   - MDPP 16 位置 + `vecmdpp`；
   - promotion 82、bypass 56/256、placement −15/35/44；
   - 训练初值 1、threshold 128、deadzone 109/135；
   - 特征用 author `single_1`（≈Table 1(a)）。
   预期：把 +3.76% 拉到 **+6–8%**；如果到不了，再查 bypass/特征。
2. **真 bypass**：加 `should_bypass` 钩子，重跑 xalan/soplex/mcf，
   量化近似误差。
3. **参数搜索**：在 MDPP 上重新搜 τ/π，看能否超过作者竞赛值。
4. **特征集 A/B**：`single_1` vs Table 1(b)，看哪套更强。

## 一句话

第一次的 +3.76% 是“MPPPB 预测器放在错误的底座和参数体系里”的结果，
不是 MPPPB 方法本身的上限；单核 MDPP + 作者参数是必须补的一步，
补完才能谈“复现”还是“改进”。