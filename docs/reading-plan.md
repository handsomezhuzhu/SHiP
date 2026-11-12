# 已有论文的主题与阅读优先级

前提：最终复现目标是 **MPPPB（MICRO 2017）**。
SHiP / SHiP++ 作为对照基线；如果改选其他论文，看文末的"换题调整"。

## 一、主题分类

| 主题 | 论文 | 在这条线里的角色 |
|---|---|---|
| **A. 替换策略基础** | DIP (ISCA'07)、RRIP/SRRIP/DRRIP (ISCA'10)、SDBP (MICRO'10)、PACMan (MICRO'11) | 提供 RRPV、set dueling、dead-block、预取感知这些"零件"；DRRIP 就是必备 baseline |
| **B. 签名/插入预测** | SHiP (MICRO'11)、**SHiP++ (CRC-2'17)**、EHC (CRC-2'17)、ReD (CRC-2'17)、MDPP (HPCA'16) | SHiP 家族本身：用 PC/签名预测该不该把新行插到低优先级 |
| **C. Belady-OPT 监督学习** | Hawkeye/Belady'16 (ISCA'16)、Harmony (ISCA'18)、Glider (MICRO'19)、Mockingjay (HPCA'22) | 用"过去如果按 OPT 会怎样"当标签，学一个二分类/多分类器；SHiP++ 之后的主要竞争对手 |
| **D. 感知机与 ML** | Perceptron Reuse (MICRO'16)、MPPPB (MICRO'17)、RLR (HPCA'21)、PARROT (ICML'20)、CARE (HPCA'23)、CacheFit (2026) | 多特征/端到端学习、低成本方案、并发感知、开销批评 |
| **E. 评测与工具** | ChampSim (arXiv'22)、IISWC'20 策略对比 | 仿真器与"怎么公平比较替换策略"的方法论 |

## 二、阅读优先级

### P0 — 必读（不读就没法动手）

| 文献 | 篇幅 | 读它要拿到什么 |
|---|---|---|
| **MPPPB** `mpppb_micro17.pdf` | 13 p | 16 个特征的参数含义、采样器训练规则、confidence/阈值/位置；能默写预测器结构 |
| **SHiP++**（可选） `shipplusplus_crc17.pdf` | 4 p | 仅作 SHiP 家族背景，不参与实验 |
| **SHiP** `ship_micro11.pdf` | 12 p | 签名、SHCT、R 位的原始定义；SHiP 与 SRRIP 的分工（只改插入，不改 victim/hit） |
| **RRIP/DRRIP** `rrip_isca10.pdf` | 12 p | RRPV 状态机、SRRIP/DRRIP、set dueling——所有实验的基线 |
| **Hawkeye** `belady_isca16.pdf`（+ `hawkeye_crc17.pdf` / slides） | 12 p | 主要对比对象；OPTgen + 采样器 + 二分类器怎么工作；slides 里有 C1–C4 结果 |
| **ChampSim** `champsim_arxiv22.pdf` | 10 p | 仿真器结构、统计口径、怎么写实验方法一节 |

### P1 — 基线与直接对照（做实验/写 related work 必看）

| 文献 | 篇幅 | 读它要拿到什么 |
|---|---|---|
| **DIP** `dip_isca07.pdf` | 11 p | set dueling 的出处（DRRIP 的 PSEL 机制） |
| **SDBP** `sdbp_micro10.pdf` | 12 p | SHiP 的主要对照；dead-block 预测与 SHiP 的区别 |
| **PACMan** `pacman_micro11.pdf` | 12 p | 预取感知插入/提升；SHiP++ Enhancement 4/5 的直接来源 |
| **Belady'16** `belady_isca16.pdf` | 12 p | "用 OPT 的过去当老师"这一整套框架，Hawkeye 的前身 |
| **Harmony** `harmony_isca18.pdf` | 14 p | CRC-2 冠军；预取感知 + MIN 近似，做偏差分析/对比很有用 |
| **Glider** `glider_micro19.pdf` | 14 p | Hawkeye 之后最强的二分类路线（离线 LSTM + 在线 SVM） |
| **Mockingjay** `mockingjay_hpca22.pdf` | 15 p | 当前 SOTA 之一，多分类复用距离预测；写"后续工作"必引 |
| **RLR** `rlr_hpca21.pdf` | 13 p | 低成本、无 PC 签名；适合做"开销-收益"对照 |

### P2 — 扩展阅读 / 找改进点（写作阶段按需）

| 文献 | 篇幅 | 用途 |
|---|---|---|
| MPPPB `mpppb_micro17.pdf` | 13 p | 多视角感知机；理解"多特征"路线 |
| Perceptron Reuse `perceptron_micro16.pdf` | 12 p | MPPPB 的前序，快速扫 |
| EHC `belady_expected_hit_count_arxiv18.pdf`（或 4 页 CRC 版） | 10 p | "期望命中数"作为训练信号，可做改进灵感 |
| ReD `red_crc17.pdf` | 4 p | CRC-2 第 3 名，复用检测 |
| MDPP `mdpp_hpca16.pdf` | 11 p | 插入/提升的另一视角 |
| CARE `care_2023.pdf` | 13 p | 并发感知的 PMC 指标；与"纯替换"互补 |
| PARROT `parrot_icml20.pdf` | 14 p | 端到端模仿学习，ML 替换的代表 |
| CacheFit `cachefit_arxiv26.pdf` | 13 p | 对 SHiP++ 等策略的面积/功耗批评，**写"不足与改进"的弹药** |
| IISWC'20 `llc_characterization_iiswc20.pdf` | 11 p | 多策略横向评测方法、偏差解释模板 |

## 三、建议阅读顺序（约 7 天，每天 2–4 小时）

1. **Day 1**：MPPPB（读 3 遍：先看 Figure 2/Table 1，再抠 16 个特征和训练规则，最后对照 v0 代码）
2. **Day 2**：RRIP（RRPV 状态机）+ SDBP（采样器与 dead block 训练）+ Perceptron'16（前序）
3. **Day 3**：SHiP + SHiP++（对照基线，重点看与 MPPPB 的差异）
4. **Day 4**：Hawkeye + Belady'16（OPT 学习框架，另一个主要对照）
5. **Day 5**：DIP + PACMan + Harmony（set dueling / 预取感知，决定实验配置）
6. **Day 6**：Glider + Mockingjay + RLR（各用 3 句话说清区别）
7. **Day 7**：CacheFit + IISWC'20 + ChampSim（开销分析、评测方法、工具细节）

> 只做复现 + 报告的话，P0 + P1 的 13 篇足够；P2 是加分项，不要平均用力。

## 四、重复版本说明（别重复读）

| 论文 | 长版 | 短版 | 建议 |
|---|---|---|---|
| Hawkeye | ISCA'16 正式版（`belady_isca16.pdf`，本地已有） | CRC-2 4 页 + 33 页 slides | 读 ISCA'16 正式版；CRC 版查预取相关差异 |
| MPPPB | MICRO'17 13 页 | CRC-2 4 页 | 读 13 页版 |
| Harmony | ISCA'18 14 页 | CRC-2 4 页 | 读 14 页版 |
| EHC | arXiv 10 页 | CRC-2 4 页 | 读 10 页版 |

## 五、如果换题，阅读清单怎么调

- **改选 Hawkeye**：P0 换成 Hawkeye 正式版 + Belady'16；SHiP++ 降为 P1（作为对照）。
- **改选 Glider / Mockingjay**：P0 加对应的 14/15 页论文，另外必须补 Hawkeye（它们是 Hawkeye 的直系后续）。
- **改选 RLR**：P0 换成 RLR + RRIP；SHiP/SHiP++ 只作背景。
- **改选 CARE**：P0 换成 CARE + IISWC'20；SHiP 系全部降为背景。