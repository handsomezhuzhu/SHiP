# 正式实验运行计划（instabox）

日期：2026-11-13。目的：在 5 台 instabox 沙箱上跑完
**LRU / SHiP-PC / MPPPB × 8 trace** 的正式矩阵，并记录每一条的
运行位置、窗口和耗时。

## 1. 平台

| 项 | 值 |
|---|---|
| 沙箱 | instabox `ci` 模板，5 台：`mpppb-a` … `mpppb-e` |
| 单台规格 | 4 vCPU / 8 GiB / 20 GiB `/data` + 80 GiB root，Ubuntu 24.04 |
| ChampSim | `develop` @ `410cee62d9c429c043ea611325ce00e6c303be2a` |
| 编译 | g++ 13.3，`-O3`；系统 `libfmt` / `liblzma` / `zlib` / `libbz2` / CLI11 headers（替代 vcpkg） |
| 公共配置 | 单核 4 GHz、LLC 2 MB 2048×16、无预取；见 `docs/baselines.md` |
| 窗口 | warmup 50 M + 测量 150 M 指令 |
| 指标 | IPC、LLC access/miss/MPKI、相对 LRU 的 IPC 比值 |
| 结果目录 | 每台 `/data/home/results/<policy>/<trace>.json` |

### 为什么放在 instabox

本机 WSL（24 核）与沙箱跑同一个 mcf 1 M+2 M 窗口：
WSL 47.7 s，沙箱 24.1 s，约 **2×**。本机还要承担编译/交互，
所以正式矩阵全部放沙箱；本机只保留代码审查、编译验证和汇总脚本。

## 2. 策略配置

- LRU：`replacement/lru`
- SHiP-PC：`replacement/ship`（ChampSim 自带，签名=插入 PC）
- MPPPB：`champsim_modules/mpppb`，阈值取本轮搜索的 c 组：

| 参数 | 值 |
|---|---|
| τ_bypass | 250 |
| τ_p1 / τ_p2 / τ_p3 | 150 / 75 / 0 |
| τ_promote (τ4) | 100 |
| π1 / π2 / π3 | 3 / 3 / 2（RRPV） |
| 采样器 | 64 组 × 18 路，1/32 sets |
| 特征 | 论文 Table 1(b) 的 16 条 |

阈值搜索记录见本文件第 5 节。

## 3. 运行矩阵与位置（24 条）

每台 4 核，4 条并行。`mpppb-a` 的 4 条：

| # | 策略 | trace | 预计耗时 | 状态 |
|---|---|---|---|---|
| A1 | LRU | 483.xalancbmk | ~67 min | queued |
| A2 | LRU | 450.soplex | ~48 min | queued |
| A3 | LRU | 429.mcf | ~33 min | queued |
| A4 | LRU | 410.bwaves | ~6 min | queued |

`mpppb-b`：

| # | 策略 | trace | 预计耗时 | 状态 |
|---|---|---|---|---|
| B1 | SHiP-PC | 483.xalancbmk | ~67 min | queued |
| B2 | SHiP-PC | 450.soplex | ~48 min | queued |
| B3 | SHiP-PC | 429.mcf | ~33 min | queued |
| B4 | SHiP-PC | 410.bwaves | ~6 min | queued |

`mpppb-c`：

| # | 策略 | trace | 预计耗时 | 状态 |
|---|---|---|---|---|
| C1 | MPPPB | 483.xalancbmk | ~67 min | queued |
| C2 | MPPPB | 450.soplex | ~48 min | queued |
| C3 | MPPPB | 429.mcf | ~33 min | queued |
| C4 | MPPPB | 410.bwaves | ~6 min | queued |

`mpppb-d`（两批）：

| # | 策略 | trace | 预计耗时 | 状态 |
|---|---|---|---|---|
| D1 | LRU | 400.perlbench | ~12 min | queued |
| D2 | SHiP-PC | 400.perlbench | ~12 min | queued |
| D3 | MPPPB | 400.perlbench | ~12 min | queued |
| D4 | LRU | 403.gcc | ~8 min | queued |
| D5 | MPPPB | 470.lbm | ~11 min | queued |
| D6 | LRU | 437.leslie3d | ~17 min | queued |
| D7 | SHiP-PC | 437.leslie3d | ~17 min | queued |
| D8 | MPPPB | 437.leslie3d | ~17 min | queued |

`mpppb-e`：

| # | 策略 | trace | 预计耗时 | 状态 |
|---|---|---|---|---|
| E1 | SHiP-PC | 403.gcc | ~8 min | queued |
| E2 | MPPPB | 403.gcc | ~8 min | queued |
| E3 | LRU | 470.lbm | ~11 min | queued |
| E4 | SHiP-PC | 470.lbm | ~11 min | queued |

合计 24 条：8 trace × 3 策略。关键路径是 xalan 的 3 条（A1/B1/C1
并行），预计 **65–75 min**；其余盒子的批次在 30 min 内结束。
若云主机负载高，按 1.3× 余量估计 ≤ 90 min。

### 实际启动记录（2026-11-12 16:22 UTC）

- 5 台全部启动，每台 `pgrep champsim` = 4，说明 4 条并行正常。
- `mpppb-a` 的 mcf/xalan 早期下载成了短名 `mcf.xz`/`xalan.xz`，
  矩阵脚本按全名找不到，首次启动 1 s 退出（rc=105）。已补软链接
  `429.mcf-22B.champsimtrace.xz -> mcf.xz`、
  `483.xalancbmk-127B.champsimtrace.xz -> xalan.xz`，并单独补跑这两条。
  其余 4 台是标准全名，无此问题。

### 实测单条耗时（50 M + 150 M，rc 全部为 0）

| trace | 实测 | 说明 |
|---|---|---|
| 410.bwaves | 380 / 401 / 410 s（6.3–6.8 min） | 与预估一致 |
| 403.gcc | 430 / 434 / 486 s（7.2–8.1 min） | 与预估一致 |
| 400.perlbench | 662 / 670 / 683 s（11.0–11.4 min） | 与预估一致 |
| 470.lbm | 1667 / 1703 / 1796 s（27.8–29.9 min） | MPPPB 最慢 |
| 483.xalancbmk | 1722 / 1822 / 1890 s（28.7–31.5 min） | **预估 67 min 偏高**；xalan 实际 IPC 0.31，但 cycles/s 高 |
| 450.soplex | 2010 / 2110 / 2184 s（33.5–36.4 min） | 预估 48–55 min 偏高 |
| 437.leslie3d | 1437 / 1439 / 1463 s（24.0–24.4 min） | |
| 429.mcf | 2175 / 2222 / 2305 s（36.3–38.4 min） | 本轮最长；MPPPB 2305 s |

> 结论：墙钟不能只按 IPC 估。同样 200 M 指令，低 IPC 的 xalan 反而比
> 高 IPC 的 gcc 只慢 3.5×，因为流水线里同时在飞的指令少、每周期模拟开销低。
> 实际关键路径是 **mcf（约 38 min）**，24 条矩阵从 16:22:03 开始，
> **17:03:30 UTC 全部结束，墙钟 41 min 27 s**。
> 5 台各 4 条并行，20 个 vCPU 有效利用率约 65%，没有超时或 OOM。

> 结论：墙钟不能只按 IPC 估。同样 200 M 指令，低 IPC 的 xalan 反而比
> 高 IPC 的 gcc 只慢 3.5×，因为流水线里同时在飞的指令少、每周期模拟开销低。
> 关键路径由 xalan 改成 **soplex / mcf**，完成时间从原估 17:30 提前到
> **约 17:10–17:20 UTC**。

## 4. 已完成的本机/沙箱验证（不计入正式矩阵）

| 平台 | 内容 | 结果 |
|---|---|---|
| WSL Ubuntu | `mpppb` 编译、mcf 1 M+2 M | IPC 0.4418，MPKI 21.97；无 crash |
| WSL Ubuntu | mcf 10 M+10 M，LRU vs MPPPB | 修复训练前两者几乎相同 → 证明训练未生效 |
| instabox-a | mcf 1 M+2 M，MPPPB | 与 WSL 完全一致（IPC 0.4418/MPKI 21.974），验证构建可复现 |
| instabox-a | 置信度分布（mcf 2 M+2 M） | fills 86 629，全部匹配 pending；bypass 23 172（27%）；buckets 见第 5 节 |
| instabox-a | 阈值/位置搜索，mcf+xalan 5 M+5 M | c 组最优：xalan +6% IPC / −8% MPKI；mcf ±0% |

## 5. 阈值搜索结果（5 M warmup + 5 M 测量）

| 组 | τ0 | τ1 | τ2 | τ3 | τ4 | π | mcf IPC | mcf MPKI | xalan IPC | xalan MPKI |
|---|---|---|---|---|---|---|---|---|---|---|
| LRU | - | - | - | - | - | - | 0.5042 | 17.742 | 0.2506 | 28.654 |
| SHiP | - | - | - | - | - | - | 0.5048 | 19.229 | - | - |
| base | 10000 | 10000 | 10000 | 10000 | -10000 | 2/2/2 | 0.5040 | 17.754 | 0.2506 | 28.657 |
| a | 10000 | 150 | 75 | 0 | 100 | 3/3/2 | 0.5052 | 18.628 | 0.2643 | 26.411 |
| c | 250 | 150 | 75 | 0 | 100 | 3/3/2 | 0.5051 | 18.429 | **0.2660** | **26.279** |
| g | 300 | 200 | 100 | 0 | 150 | 3/3/2 | 0.5036 | 18.444 | 0.2647 | 26.359 |
| h | 250 | 150 | 75 | -50 | 100 | 3/3/2 | 0.5043 | 18.618 | 0.2660 | 26.279 |
| k | 400 | 200 | 100 | 0 | 100 | 3/3/2 | 0.5041 | 18.429 | 0.2646 | 26.359 |

说明：
- `base` 是“预测器不起作用”的对照（所有 fill 放 RRPV=2、命中不提升），
  在 mcf/xalan 上几乎与 LRU 相同，说明当前 MPPPB 的差异来自预测器本身。
- `c` 的 bypass 在 xalan 上占 58% fills（250 门槛），仍比不 bypass 的 `a`
  略好；在 mcf 上 bypass 约 8%。
- 选择 `c` 作为正式矩阵配置。

## 6. 汇总与产出

每台箱子跑完后：
1. 把 `/data/home/results/<policy>/*.json` 拉回本机
   `results/raw/champsim/<policy>/`；
2. `python3 scripts/summarize_champsim.py results/raw/champsim results/champsim_results.csv`；
3. 生成逐 trace 的 IPC / MPKI / 相对 LRU 表 + 几何平均；
4. 报告里写明偏差：SRRIP 底座（论文单核 MDPP）、bypass 近似、
   LLC 访问级 PC 历史、τ/π 为搜索值、SPEC2017 vs 2006。

## 7. 复现命令（单台）

```bash
# 环境（已由 setup_box.sh 完成）
sudo apt-get install -y build-essential git cmake liblzma-dev zlib1g-dev \
  libbz2-dev libfmt-dev libcli11-dev nlohmann-json3-dev xz-utils

cd ~/ChampSim
./config.sh --replacement-dir ~/champsim_modules ~/configs/champsim_mpppb.json
make -j4

# 一条
MPPPB_TAU_BYPASS=250 MPPPB_TAU_P1=150 MPPPB_TAU_P2=75 MPPPB_TAU_P3=0 \
MPPPB_TAU_PROMOTE=100 MPPPB_POS1=3 MPPPB_POS2=3 MPPPB_POS3=2 \
bin/champsim_mpppb -w 50000000 -i 150000000 --hide-heartbeat --json out.json \
  traces/429.mcf-22B.champsimtrace.xz
```