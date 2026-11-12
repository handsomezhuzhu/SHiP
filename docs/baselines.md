# 三条对比策略的确切配置

最终实验范围：**LRU / SHiP-PC / MPPPB**。三条策略都跑同一个 ChampSim 配置，
只替换 LLC 的 `replacement` 模块。

## 公共平台配置

| 参数 | 值 |
|---|---|
| ChampSim | develop @ `410cee62d9c429c043ea611325ce00e6c303be2a` |
| 核数 | 1（后续可扩 4 核） |
| 频率 | 4 GHz |
| 前端 | 6-wide，352-entry ROB |
| L1I | 32 KB，8-way，4 cycle |
| L1D | 32 KB，12-way，5 cycle |
| L2 | 256 KB，1024 sets × 8-way，10 cycle |
| **LLC** | **2 MB，2048 sets × 16-way，20 cycle** |
| 预取器 | 关闭（v1 可加 `next_line`） |
| 统计 | warmup 50 M 指令 + 测量 150 M 指令 |
| 指标 | IPC、LLC access/miss/MPKI、几何平均 |

配置文件：`configs/champsim_{lru,ship,mpppb}.json`
（`ship` 即 SHiP-PC；避免文件名歧义，报告里统一写 **SHiP-PC**。）

## 1. LRU

- 模块：ChampSim 自带 `replacement/lru`
- 规则：命中/插入都放到 MRU；受害者是 LRU 行
- 作用：基线，所有 speedup 都相对它归一化

## 2. SHiP-PC（ChampSim `replacement/ship`）

对应 SHiP 论文里的 **SHiP-PC** 签名（signature = miss-causing PC），并带 set sampling。

| 参数 | 值 |
|---|---|
| 签名 | 插入指令的 PC（`ip`），取低 32 bit |
| SHCT | 16384 项 × 3-bit 饱和计数器，索引 `pc % 16381` |
| 采样 | 只对采样组维护签名/R 位；ChampSim `msl` 对 2048 sets 的采样率是 **1/8（256 组）** |
| RRPV | 2-bit，`maxRRPV = 3` |
| 插入 | SHCT 饱和（7）→ RRPV=3；否则 RRPV=2 |
| 命中 | RRPV=0；命中时 SHCT−1，逐出未复用时 SHCT+1 |
| 备注 | ChampSim 的计数器语义与 SHiP 原文相反（原文"复用越多值越大"），但预测效果等价方向；报告里需注明 |

> 原文 SHiP 用 32–64 个采样组；ChampSim 的 `msl` 采样率算法给出 256 组。
> 这是 SHiP-PC 基线相对原文的一个偏差，但三条策略都使用同一套 ChampSim，
> 横向比较仍然成立。报告里单独说明。

## 3. MPPPB（本仓库 `champsim_modules/mpppb`）

| 参数 | 值 | 与论文 |
|---|---|---|
| 特征 | 论文 Table 1(b) 的 16 个单线程特征 | 一致 |
| 权重表 | 每特征一张，6-bit 有符号（−32…+31） | 一致 |
| 采样器 | **64 组**（1/32 sets），18-way，LRU | 一致 |
| 采样条目 | partial tag 16-bit、confidence、特征索引向量、位置 | 一致（位宽按实现简化） |
| 训练 | live：位置 < A 时 −1；dead：越过 A 或被逐出 +1 | 一致 |
| 决策 | `conf ≥ τ_bypass` → bypass；否则按 `τ_p1/τ_p2/τ_p3` 插不同位置；`conf < τ_p3` 插 MRU；命中 `conf ≥ τ_promote` 不提升 | 一致（τ 值需搜索） |
| 底座 | **SRRIP（4 位置）** | 偏差：论文单核用 static MDPP（16 位置） |
| bypass | 插入 RRPV=3 + 标记优先逐出 | 偏差：真正 bypass 不分配 |
| 阈值（Matrix-1） | `250 / 150 / 75 / 0 / 100`（τ0/τ1/τ2/τ3/τ4） | 搜索值，论文未给 |
| 位置（Matrix-1） | `3 / 3 / 2`（RRPV，π1/π2/π3） | 搜索值；4 级 SRRIP 下 |
| 训练 | 感知机“错才训练”：live 仅在 `conf≥0` 时 −1；dead 仅在 `conf≤0` 时 +1；采样器逐出不训练 | 与论文 §3.8 语义一致 |
| 阈值/位置覆盖 | `MPPPB_TAU_*` 与 `MPPPB_POS1..3` 环境变量 | 便于搜索 |
| 代码状态 | 2026-11-12 重写 v1：特征索引/训练/放置/bypass 修复；`src/cache.cc` 两行 offset 补丁 | 见 `docs/review_mpppb_code.md` |

> Matrix-1 的完整结果见 `docs/results_matrix1.md`。旧版占位阈值
> `150/100/50/0/0` 已弃用；正式实验使用 c 组 `250/150/75/0/100`。

## 实验矩阵（计划）

| 维度 | 取值 |
|---|---|
| trace | 8 条 SPEC CPU2017（DPC-3），见 `docs/benchmark.md` |
| 策略 | LRU、SHiP-PC、MPPPB |
| 窗口 | warmup 50 M + 150 M |
| 配置 | 单核无预取；后续加 4 核、`next_line` |
| 输出 | `results/champsim_results.csv`（IPC / LLC MPKI） |

## 运行命令

```bash
# 编译三条策略
./scripts/build_policies.sh   # lru/srrip/drrip/ship
./scripts/build_mpppb.sh      # mpppb

# 只跑三条
POLICIES="lru ship mpppb" ./scripts/run_champsim.sh

# 汇总
python3 scripts/summarize_champsim.py results/raw/champsim results/champsim_results.csv
```

## 报告里必须写明的偏差

1. SHiP-PC 的采样组数（ChampSim 256 vs 原文 32–64）；
2. SHiP-PC 的计数器方向与原文相反（ChampSim 实现选择）；
3. MPPPB 的底座是 SRRIP，不是 static MDPP；
4. bypass 是"插入后优先逐出"的近似；
5. 阈值/位置是搜索得到，不是论文原值；
6. workload 用 SPEC CPU2017，原文是 SPEC CPU2006 + 自研模拟器。