# 论文清单（SHiP / LLC 缓存替换方向）

下载脚本：`scripts/fetch_papers.sh`（`papers/pdf/` 不入库）。
标注 ✅ 的已保存在本地；❌ 的需要用校园网 / 图书馆权限获取。

## 一、核心脉络

| # | 论文 | 会议 / 年份 | 一句话 | 本地文件 | 状态 |
|---|---|---|---|---|---|
| 1 | SHiP: Signature-based Hit Predictor for High Performance Caching | MICRO 2011 | 用 load PC 签名 + SHCT 学习再引用行为，指导 RRIP 插入 | `ship_micro11.pdf` | ✅ |
| 2 | SHiP++: Enhancing Signature-Based Hit Predictor for Improved Cache Performance | CRC-2 @ ISCA 2017 | 改进 SHCT 训练方式/预测粒度（CRC 第 2 名） | — | ❌ |
| 3 | Perceptron Learning for Reuse Prediction | MICRO 2016 | 用感知机组合多特征做复用预测 | `perceptron_micro16.pdf` | ✅ |
| 4 | Multiperspective Reuse Prediction (MPPPB) | MICRO 2017 | 多视角感知机 + 采样器，驱动插入/提升/bypass | `mpppb_micro17.pdf` | ✅ |
| 5 | Hawkeye: Leveraging Belady's Algorithm for Improved Cache Replacement | ISCA 2017 | 用 Belady OPT 在历史上生成监督信号，在线训练二分类器 | `hawkeye_crc17.pdf`（CRC-2 版） | ⚠️ 仅 CRC 版 |
| 6 | Applying Deep Learning to the Cache Replacement Problem (Glider) | MICRO 2019 | 离线 LSTM 提取控制流特征 → 在线 SVM 预测 | `glider_micro19.pdf` | ✅ |
| 7 | Effective Mimicry of Belady's MIN Policy (Mockingjay) | HPCA 2022 | 多分类复用距离预测，直接逼近 MIN | `mockingjay_hpca22.pdf` | ✅ |
| 8 | Designing a Cost-Effective Cache Replacement Policy using Machine Learning (RLR) | HPCA 2021 | 低成本、无需 PC 签名的 ML 替换策略 | `rlr_hpca21.pdf` | ✅ |
| 9 | CARE: A Concurrency-Aware Enhanced Lightweight Cache Management Framework | HPCA 2023 | 用 PMC 指标做并发感知的轻量缓存管理 | `care_2023.pdf` | ✅ |
| 10 | CacheFit: The Rising Cost of Cache Replacement and Constraint-Driven Redesign of LLC Replacement Policies | arXiv 2026 | 重新审视各策略的存储/功耗开销，约束驱动重设计 | `cachefit_arxiv26.pdf` | ✅ |

## 二、方法与背景

| # | 论文 | 会议 / 年份 | 用途 | 本地文件 | 状态 |
|---|---|---|---|---|---|
| 11 | Back to the Future: Leveraging Belady's Algorithm for Improved Cache Replacement | ISCA 2016 | Hawkeye 的前身；OPT 学习框架 | `belady_isca16.pdf` | ✅ |
| 12 | Rethinking Belady's Algorithm to Accommodate Prefetching (Harmony) | ISCA 2018 | 预取感知的 MIN 近似，CRC-2 冠军 | `harmony_isca18.pdf` | ✅ |
| 13 | Characterizing the Impact of Last-Level Cache Replacement Policies on Big-Data Workloads | IISWC 2020 | 各策略（含 SHiP/Glider/Hawkeye/MPPPB）横向评测方法 | `llc_characterization_iiswc20.pdf` | ✅ |
| 14 | Minimal Disturbance Placement and Promotion (MDPP) | HPCA 2016 | 插入/提升策略的另一种思路 | `mdpp_hpca16.pdf` | ✅ |
| 15 | Making Belady-Inspired Replacement Policies More Effective Using Expected Hit Count | arXiv 2018 | 对 Belady 类策略的改进分析 | `belady_expected_hit_count_arxiv18.pdf` | ✅ |
| 16 | An Imitation Learning Approach for Cache Replacement (PARROT) | ICML 2020 | 端到端模仿学习，可作为"ML 替换"对照 | `parrot_icml20.pdf` | ✅ |

## 三、待获取（建议走校园网 / 图书馆）

| 论文 | 出处 | 备注 |
|---|---|---|
| SHiP++ (Young, Chou, Jaleel, Qureshi) | CRC-2 Workshop @ ISCA 2017 | 未检索到公开 PDF；可尝试作者主页、CRC 官网或图书馆文献传递 |
| Hawkeye 正式版 | ISCA 2017, DOI 10.1145/3079856.3080222 | 本地只有 CRC-2 的 4 页版本；正式版在 ACM DL |
| Cache Replacement Policies（Jain & Lin 专著） | Morgan & Claypool, 2019 | 综述性教材，适合写 related work，图书馆可能有电子版 |
| ReD / Leeway（CRC-2 第 3 名等） | CRC-2 @ ISCA 2017 | 作为对比基线时再补 |
| SPEC CPU2006 的 CRC-2 trace | CRC 官网 / Google Drive | 若要严格对齐 Hawkeye/SHiP++ 原文实验，需要 2006 trace |

## 四、获取说明

- Princeton / UT Austin / Texas A&M / UMN / IIT 的作者主页均可直接下载，无需登录。
- ACM DL、IEEE Xplore 上的版本需要校园网 IP 或机构账号；若用学校账号下载，注意不要外传。
- 所有链接记录在 `papers/manifest.tsv`，重跑 `scripts/fetch_papers.sh` 即可补齐可公开获取的部分。