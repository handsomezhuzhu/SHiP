# 实验机工作流：拉取 → 校验 → 删机器

用户要求：**产出全部拉回本机并确认没问题后，才删除 instabox 机器**；
机器额度要留给其他 CI 使用。以后每一轮矩阵都按这个顺序执行。

## 1. 拉取

每台机器的结果目录：`/data/home/results/<policy>/<trace>.json`
（同目录还有 `.err` 与 `.time`，一起拉）。

```powershell
$ib = "C:\Users\26586\AppData\Local\Programs\instabox\instabox.exe"
$b64 = & $ib exec mpppb-a -- 'cd /data/home && tar czf - results | base64 -w0'
[IO.File]::WriteAllBytes("$env:TEMP\res_a.tar.gz", [Convert]::FromBase64String($b64))
```

本机解包到统一的矩阵目录（不要和旧结果混在一起）：

```bash
rm -rf results/raw/matrix1 && mkdir -p results/raw/matrix1
tar xzf /mnt/c/.../res_a.tar.gz -C /tmp/matrix1_a
cp -r /tmp/matrix1_a/results/. results/raw/matrix1/
```

## 2. 校验（删机器前必须做）

```bash
python scripts/summarize_champsim.py results/raw/matrix1 results/matrix1_results.csv
python scripts/verify_results.py --root results/raw/matrix1 \
    --csv results/matrix1_results.csv
```

`verify_results.py` 会检查：

- 每个 `(policy, trace)` 的 JSON 存在且能解析；
- `instructions` 在 150 M 窗口内（可改 `--min-instr/--max-instr`）；
- `cycles > 0`，`.time` 存在且为正；
- `.err` 里没有 `panic/deadlock/error/abort/out_of_range`；
- CSV 行数 = trace × policy，IPC/MPKI 与 JSON 一致；
- 顺带打印相对 LRU 的几何平均。

**只有输出 `bad NONE` 才允许删机器。** 有缺失/异常时先补跑，
补跑仍失败就保留机器排查，不要删。

## 3. 留档

- 原始 JSON：`results/raw/matrix1/`（`.gitignore` 忽略，仅本机保留）；
- 汇总 CSV：`results/matrix1_results.csv`（提交）；
- 对比表：`results/matrix1_comparison.md`（提交）；
- 结果分析：`docs/results_<matrix>.md`（提交）；
- 运行计划/实际耗时：`docs/run_plan.md`（提交）。

## 4. 删机器

校验通过、留档完成后：

```powershell
$ib = "C:\Users\26586\AppData\Local\Programs\instabox\instabox.exe"
foreach ($b in @('mpppb-e','mpppb-d','mpppb-c','mpppb-b','mpppb-a')) {
  & $ib rm $b --no-wait
}
& $ib ls    # 必须显示 0/5
& $ib usage # 确认存储/机器数回落
```

不要只 `suspend`：paused 机器仍占用 5/5 额度。**删掉**才真正释放。

## 5. 当前状态（2026-11-13）

- Matrix-1 的 24 条已校验：`json_count 24`、`csv_rows 24`、`bad NONE`；
- 5 台 `mpppb-a…e` 已删除，`instabox ls` = 0/5；
- 产物在 `results/raw/matrix1/`、`results/matrix1_*`、`docs/results_matrix1.md`；
- 需要复跑时用 `scripts/instabox_setup.sh` 重建环境（约 10 min/台）。