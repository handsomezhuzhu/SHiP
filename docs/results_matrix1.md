# Matrix-1 正式结果（2026-11-12/13）

24 条 = 8 trace × 3 策略，全部在 instabox 上完成，`rc=0`。
原始数据：`results/raw/matrix1/<policy>/<trace>.json`；
汇总 CSV：`results/matrix1_results.csv`；对比表：`results/matrix1_comparison.md`。

## 1. 平台与窗口

| 项 | 值 |
|---|---|
| 机器 | instabox `ci`，5 台：`mpppb-a` … `mpppb-e`，每台 4 vCPU / 8 GiB |
| ChampSim | `develop` @ `410cee62d9c429c043ea611325ce00e6c303be2a` |
| 编译 | g++ 13.3，`-O3`，系统 libfmt/liblzma/zlib/bz2 + CLI11 headers |
| 公共配置 | 单核 4 GHz、LLC 2 MB 2048×16、无预取 |
| 窗口 | warmup 50 M + 测量 150 M 指令（JSON 里 `instructions=15000000x`） |
| 策略 | LRU；SHiP-PC（ChampSim `ship`）；MPPPB（本仓库） |
| MPPPB 参数 | τ0=250, τ1=150, τ2=75, τ3=0, τ4=100；π=3/3/2 |

## 2. 逐 trace 结果

| trace | LRU IPC | SHiP IPC | MPPPB IPC | MPPPB/LRU | SHiP/LRU | LRU MPKI | SHiP MPKI | MPPPB MPKI |
|---|---|---|---|---|---|---|---|---|
| 400.perlbench-41B | 1.3182 | 1.3459 | 1.3379 | 1.0149 | 1.0210 | 0.57 | 0.46 | 0.49 |
| 403.gcc-16B | 2.1750 | 2.1747 | 2.1743 | 0.9997 | 0.9999 | 0.15 | 0.15 | 0.16 |
| 410.bwaves-945B | 3.0102 | 3.0102 | 3.0102 | 1.0000 | 1.0000 | 0.02 | 0.02 | 0.02 |
| 429.mcf-22B | 0.3193 | 0.3242 | 0.3243 | 1.0157 | 1.0153 | 28.75 | 30.80 | 29.58 |
| 437.leslie3d-134B | 0.6252 | 0.6232 | 0.6247 | 0.9992 | 0.9968 | 7.40 | 7.74 | 7.42 |
| 450.soplex-92B | 0.3097 | 0.3544 | 0.3489 | **1.1266** | **1.1443** | 23.27 | 20.06 | **19.77** |
| 470.lbm-1274B | 0.6150 | 0.6129 | 0.6200 | 1.0081 | 0.9966 | 28.49 | 33.99 | 28.96 |
| 483.xalancbmk-127B | 0.2588 | 0.3076 | 0.2974 | **1.1491** | **1.1886** | 28.02 | 21.95 | 22.96 |

几何平均（8 条，speedup 相对 LRU；MPKI 比值越低越好）：

| 策略 | 几何平均 IPC vs LRU | 几何平均 MPKI vs LRU |
|---|---|---|
| SHiP-PC | **1.0430（+4.30%）** | 0.9631（−3.69%） |
| MPPPB | 1.0376（+3.76%） | **0.9498（−5.02%）** |

## 3. 解读

1. **MPPPB 与 SHiP 都优于 LRU**：MPPPB +3.76% IPC、MPKI −5.02%；
   SHiP +4.30% IPC、MPKI −3.69%。两者在几何平均上只差 0.5 个百分点。
2. **收益集中在 LLC 压力大的 workload**：soplex（MPPPB +12.7%，
   SHiP +14.4%）和 xalan（+14.9% / +18.9%）。bwaves/gcc 这类 LLC
   几乎不缺失的 trace 三者完全相同。
3. **MPPPB 的 MPKI 最低**，但 IPC 略低于 SHiP。原因是 mcf/lbm 上
   MPPPB 的 miss 更少但 IPC 增益有限，而 SHiP 在 soplex/xalan 上的
   IPC 增益更大。
4. **SHiP 在 lbm 上明显退化**：IPC −0.34%，MPKI +19.3%（28.49→33.99）；
   MPPPB 在 lbm 上 MPKI +1.6%、IPC +0.8%，更稳。
5. **mcf 的 IPC/MPKI 解耦**：MPPPB IPC +1.57% 但 MPKI +2.9%；
   SHiP IPC +1.53% 但 MPKI +7.1%。miss 更多却更快，说明 miss
   的时间分布/DRAM 拥塞不同，单看 MPKI 会误判。
6. **与论文的差距**：论文单核 +9.0% over LRU（MDPP 底座、SPEC2006、
   99 segments、真实 bypass）。本复现 +3.76%，主要偏差见第 5 节。
   论文的主对比是 Hawkeye（+5.1%）和 Perceptron（+6.3%），SHiP 只是
   同族参照，不在原文主表里。

## 4. 实际耗时与墙钟

| trace | LRU | SHiP | MPPPB |
|---|---|---|---|
| 410.bwaves | 380 s | 401 s | 410 s |
| 403.gcc | 486 s | 430 s | 434 s |
| 400.perlbench | 683 s | 662 s | 670 s |
| 437.leslie3d | 1463 s | 1437 s | 1439 s |
| 470.lbm | 1667 s | 1703 s | 1796 s |
| 483.xalancbmk | 1890 s | 1722 s | 1822 s |
| 450.soplex | 2184 s | 2010 s | 2110 s |
| 429.mcf | 2175 s | 2222 s | 2305 s |

- 单核累计：LRU 3.04 h、SHiP 2.94 h、MPPPB 3.05 h，共 **9.03 CPU-hours**；
- 5 台 × 4 条并行，**16:22:03 → 17:03:30 UTC，墙钟 41 min 27 s**；
- 20 vCPU 的有效利用率约 65%（短任务先结束，长尾是 mcf）；
- 无 OOM、无超时、24 条全部 `rc=0`。

> 经验：墙钟不能只用 IPC 估。xalan 的 IPC 只有 0.31，但模拟器
> cycles/s 高，200 M 指令只用 28–32 min；lbm 的 IPC 0.615，
> 反而要 28–30 min；mcf 最慢 36–38 min。

## 5. 已知偏差（报告必须写）

1. **底座**：本实现用 SRRIP（4 位置），论文单核用 static MDPP（16 位置
   + 树状 pseudo-LRU）。这是最大的结构性偏差。
2. **bypass 近似**：论文真正“不分配”；本实现插入到 RRPV=3 并标记
   优先逐出，块仍占 LLC。xalan 上 bypass 占 58% fills，近似可能低估收益。
3. **τ/π 未在完整窗口调优**：c 组是在 mcf+xalan 的 5 M+5 M 上搜的，
   不是 150 M 窗口的最优值；也没有逐 trace 调参。
4. **PC 历史**：本实现只在 LLC 访问上更新 PC 环形缓冲；论文是每个
   memory access 都更新。LLC 过滤后序列更稀疏。
5. **workload**：SPEC CPU2017（DPC-3）vs 论文 SPEC CPU2006；
   每 benchmark 1 条 trace vs 论文 99 个 simpoint segment。
6. **SHiP-PC 基线**：ChampSim 的 `msl` 采样率是 1/8（256 组），
   原文 32–64 组；计数器方向也与原文相反。三条策略共用同一
   ChampSim，横向比较仍成立，但绝对值不能直接对齐论文。
7. **单核、无预取**：论文有 stream prefetcher；本矩阵关闭，
   无法体现 bypass 在预取污染下的作用。
8. **ChampSim 核心补丁**：为让 offset 特征看到块内偏移，改了
   `src/cache.cc` 两行（把未对齐地址传给 replacement 模块），
   有注释，可回退；对 LRU/SHiP 无行为影响。补丁文件：
   `champsim_modules/mpppb/cache_offset.patch`。

## 6. 复现

```bash
# 1) 5 台 instabox（ci 模板），每台：
bash scripts/instabox_setup.sh        # apt + clone + patch + 3 binaries + 8 traces

# 2) 每台按分配跑（示例：A 箱）
bash scripts/instabox_matrix.sh \
  lru:483.xalancbmk-127B lru:450.soplex-92B lru:429.mcf-22B lru:410.bwaves-945B

# 3) 结果汇总
python scripts/summarize_champsim.py results/raw/matrix1 results/matrix1_results.csv
python scripts/compare_policies.py results/matrix1_results.csv
```

## 7. 下一步

1. **实现 static MDPP**（16 位置 + 树状 pseudo-LRU），替换 SRRIP 底座，
   这是最可能把 +3.8% 拉向论文 +9% 的一步。
2. **真 bypass**：在 `CACHE::handle_fill` 增加 `should_bypass` 钩子，
   跳过分配；量化 xalan 上 58% bypass 的真实收益。
3. **完整窗口重调 τ/π**：用 50 M+150 M 的 2–3 条 trace 做小网格，
   或按 workload 分类调参；记录搜索过程。
4. **补 Hawkeye / Perceptron**：论文主对比是这两个；有了它们才能
   直接对照论文的 +5.1% / +6.3%。
5. **4 核 + 预取器**：multi-programmed 是论文的另一半贡献（+8.3%）。
6. **更多 trace/benchmark**：每 benchmark 2–3 条，降低单 trace 噪声。