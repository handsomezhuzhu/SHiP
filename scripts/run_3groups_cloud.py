#!/usr/bin/env python3
"""Orchestrate the 3-group generalization experiment across 5 Instabox + 3 Daytona VMs.

Groups:
  1. g1_old_spp  : 8 SPEC2006 (traces/) x 4 policies (L1D next_line + L2C spp_dev) = 32 runs
  2. g2_new_pref : 20 new traces (traces_new/) x 4 policies (L1D next_line + L2C ip_stride) = 80 runs
  3. g3_new_spp  : 20 new traces (traces_new/) x 4 policies (L1D next_line + L2C spp_dev) = 80 runs
Total = 192 simulation runs across 8 cloud sandboxes (5x4 Instabox + 3x4/2 Daytona).

Usage:
  python scripts/run_3groups_cloud.py --plan
  python scripts/run_3groups_cloud.py --group all --daytona-snapshot daytona-large
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

_IB_META_LOCK = threading.Lock()

ROOT = pathlib.Path(__file__).resolve().parent.parent
DAYTONA_ENV = ROOT / "env" / "daytona.env"
INSTABOX_EXE = os.environ.get("INSTABOX_EXE", r"C:\Users\26586\AppData\Local\Programs\instabox\instabox.exe")
DAYTONA_API = "https://app.daytona.io/api"
DAYTONA_TARGET = "us"

CONFIGS_TO_BUILD = [
    "lru_pref",
    "ship_pref",
    "mpppb_mdpp_pref",
    "lru_spp",
    "ship_spp",
    "mpppb_mdpp_spp",
]

GROUP_POLICIES = {
    "g1_old_spp": [
        ("lru_spp", "champsim_lru_spp", ""),
        ("ship_spp", "champsim_ship_spp", ""),
        ("mpppb_spp", "champsim_mpppb_mdpp_spp", "author2"),
        ("ta_mpppb_spp", "champsim_mpppb_mdpp_spp", "ta_mpppb"),
    ],
    "g2_new_pref": [
        ("lru_pref", "champsim_lru_pref", ""),
        ("ship_pref", "champsim_ship_pref", ""),
        ("mpppb_pref", "champsim_mpppb_mdpp_pref", "author2"),
        ("ta_mpppb_pref", "champsim_mpppb_mdpp_pref", "ta_mpppb"),
    ],
    "g3_new_spp": [
        ("lru_spp", "champsim_lru_spp", ""),
        ("ship_spp", "champsim_ship_spp", ""),
        ("mpppb_spp", "champsim_mpppb_mdpp_spp", "author2"),
        ("ta_mpppb_spp", "champsim_mpppb_mdpp_spp", "ta_mpppb"),
    ],
}


@dataclass(frozen=True)
class TraceMeta:
    name: str
    folder: str  # "traces" or "traces_new"
    suite: str
    mb: float
    warmup: int
    sim: int
    est_sec: int  # estimated CPU-seconds per single run


OLD_TRACES: list[TraceMeta] = [
    TraceMeta("400.perlbench-41B", "traces", "spec2006", 177.7, 50_000_000, 150_000_000, 640),
    TraceMeta("403.gcc-16B", "traces", "spec2006", 383.7, 50_000_000, 150_000_000, 475),
    TraceMeta("410.bwaves-945B", "traces", "spec2006", 49.1, 50_000_000, 150_000_000, 400),
    TraceMeta("429.mcf-22B", "traces", "spec2006", 534.3, 50_000_000, 150_000_000, 1680),
    TraceMeta("437.leslie3d-134B", "traces", "spec2006", 292.7, 50_000_000, 150_000_000, 840),
    TraceMeta("450.soplex-92B", "traces", "spec2006", 560.7, 50_000_000, 150_000_000, 1350),
    TraceMeta("470.lbm-1274B", "traces", "spec2006", 661.7, 50_000_000, 150_000_000, 1400),
    TraceMeta("483.xalancbmk-127B", "traces", "spec2006", 648.2, 50_000_000, 150_000_000, 1580),
]

NEW_TRACES: list[TraceMeta] = [
    # 10 DPC-3 SPEC CPU2017 Speed (6xx)
    TraceMeta("600.perlbench_s-210B", "traces_new", "dpc3_6xx", 148.2, 50_000_000, 150_000_000, 600),
    TraceMeta("602.gcc_s-734B", "traces_new", "dpc3_6xx", 351.6, 50_000_000, 150_000_000, 750),
    TraceMeta("605.mcf_s-1554B", "traces_new", "dpc3_6xx", 158.5, 50_000_000, 150_000_000, 1650),
    TraceMeta("607.cactuBSSN_s-2421B", "traces_new", "dpc3_6xx", 245.2, 50_000_000, 150_000_000, 700),
    TraceMeta("619.lbm_s-2676B", "traces_new", "dpc3_6xx", 735.8, 50_000_000, 150_000_000, 1400),
    TraceMeta("620.omnetpp_s-874B", "traces_new", "dpc3_6xx", 765.1, 50_000_000, 150_000_000, 1550),
    TraceMeta("623.xalancbmk_s-10B", "traces_new", "dpc3_6xx", 558.0, 50_000_000, 150_000_000, 1600),
    TraceMeta("649.fotonik3d_s-1176B", "traces_new", "dpc3_6xx", 313.5, 50_000_000, 150_000_000, 900),
    TraceMeta("654.roms_s-1390B", "traces_new", "dpc3_6xx", 462.2, 50_000_000, 150_000_000, 950),
    TraceMeta("657.xz_s-2302B", "traces_new", "dpc3_6xx", 496.2, 50_000_000, 150_000_000, 1100),
    # 4 Zenodo 20043527 (GAP + XSBench)
    TraceMeta("bfs.twitter-10B", "traces_new", "zenodo_gap_xs", 108.9, 50_000_000, 150_000_000, 1300),
    TraceMeta("pr.web-16B", "traces_new", "zenodo_gap_xs", 265.3, 50_000_000, 150_000_000, 1300),
    TraceMeta("sssp.web-1185B", "traces_new", "zenodo_gap_xs", 339.7, 50_000_000, 150_000_000, 1300),
    TraceMeta("xs.XL64unionized-66B", "traces_new", "zenodo_gap_xs", 162.0, 50_000_000, 150_000_000, 1300),
    # 3 Zenodo 10199624 (CVP-1, ~30M instr single-pass window verified per trace)
    TraceMeta("cvp1_srv_40", "traces_new", "zenodo_cvp1", 15.4, 5_000_000, 25_000_000, 220),
    TraceMeta("cvp1_compute_int_38", "traces_new", "zenodo_cvp1", 12.3, 5_000_000, 25_000_000, 200),
    TraceMeta("cvp1_compute_fp_8", "traces_new", "zenodo_cvp1", 9.3, 5_000_000, 25_000_000, 200),
    # 3 Zenodo 14045186 (Qualcomm Server, ~79-120M single-pass window)
    TraceMeta("qc_srv0_ap", "traces_new", "zenodo_qualcomm", 52.3, 15_000_000, 60_000_000, 550),
    TraceMeta("qc_srv106_ap", "traces_new", "zenodo_qualcomm", 85.6, 15_000_000, 60_000_000, 550),
    TraceMeta("qc_srv115_ap", "traces_new", "zenodo_qualcomm", 85.9, 15_000_000, 60_000_000, 550),
]


@dataclass
class JobSpec:
    group: str
    pol: str
    binary: str
    profile: str
    trace: TraceMeta


@dataclass
class NodeSlot:
    name: str
    provider: str  # "instabox" or "daytona"
    index: int     # 1..5 or 1..3
    vcpus: int
    disk_mb_cap: int
    jobs: list[JobSpec]
    traces: dict[str, TraceMeta]
    est_cpu_sec: float = 0.0
    trace_mb: float = 0.0


def existing_json_ok(group: str, pol: str, trace_name: str) -> bool:
    p = ROOT / "results" / "raw" / group / pol / f"{trace_name}.json"
    if not p.exists() or p.stat().st_size < 100:
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        return bool(data and data[0].get("sim", {}).get("cores", [{}])[0].get("cycles", 0) > 0)
    except Exception:
        return False


def collect_trace_bundles(selected_groups: list[str], skip_existing: bool = True) -> list[tuple[TraceMeta, list[JobSpec]]]:
    bundles: dict[str, tuple[TraceMeta, list[JobSpec]]] = {}
    group_defs = {
        "1": ("g1_old_spp", OLD_TRACES),
        "2": ("g2_new_pref", NEW_TRACES),
        "3": ("g3_new_spp", NEW_TRACES),
    }
    for g_key in selected_groups:
        g_name, tr_list = group_defs[g_key]
        for tr in tr_list:
            for pol, binary, profile in GROUP_POLICIES[g_name]:
                if skip_existing and existing_json_ok(g_name, pol, tr.name):
                    continue
                if tr.name not in bundles:
                    bundles[tr.name] = (tr, [])
                bundles[tr.name][1].append(JobSpec(g_name, pol, binary, profile, tr))
    items = list(bundles.values())
    items.sort(key=lambda kv: (len(kv[1]) * kv[0].est_sec), reverse=True)
    return items


def assign_shards(bundles: list[tuple[TraceMeta, list[JobSpec]]], daytona_vcpus: int, daytona_disk_cap_mb: int) -> list[NodeSlot]:
    nodes = [
        NodeSlot(f"ib-gen-{i}", "instabox", i, vcpus=4, disk_mb_cap=12_000, jobs=[], traces={})
        for i in range(1, 6)
    ] + [
        NodeSlot(f"dt-gen-{i}", "daytona", i, vcpus=daytona_vcpus, disk_mb_cap=daytona_disk_cap_mb, jobs=[], traces={})
        for i in range(1, 4)
    ]

    for tr, jlist in bundles:
        work_sec = sum(j.trace.est_sec for j in jlist)
        eligible = [n for n in nodes if (n.trace_mb + tr.mb) <= n.disk_mb_cap]
        if not eligible:
            eligible = [n for n in nodes if n.provider == "instabox"]

        def score(n: NodeSlot) -> float:
            # Wave-aware completion cost plus Daytona upload time (~5 MB/s)
            up_pen = (tr.mb / 5.0) if n.provider == "daytona" else (tr.mb / 40.0)
            return (n.est_cpu_sec + work_sec) / n.vcpus + up_pen

        best = min(eligible, key=score)
        best.traces[tr.name] = tr
        best.jobs.extend(jlist)
        best.est_cpu_sec += work_sec
        best.trace_mb += tr.mb

    return nodes


def build_payload_tarball(out_path: pathlib.Path) -> pathlib.Path:
    """Pack ChampSim source + mpppb module + 6 configs + setup/run helpers (< 2 MB)."""
    cs = ROOT / "env" / "ChampSim"
    keep_dirs = ("inc", "src", "branch", "btb", "prefetcher", "replacement", "config")
    keep_files = ("Makefile", "config.sh", "champsim_config.json", "global.options", "module.options")
    with tarfile.open(out_path, "w:gz") as tf:
        for d in keep_dirs:
            tf.add(cs / d, arcname=f"ChampSim/{d}", filter=lambda ti: None if ti.name.endswith((".o", ".d")) else ti)
        for fn in keep_files:
            tf.add(cs / fn, arcname=f"ChampSim/{fn}")
        tf.add(ROOT / "champsim_modules", arcname="champsim_modules")
        tf.add(ROOT / "scripts" / "get_ext_traces.py", arcname="scripts/get_ext_traces.py")
        for cfg in CONFIGS_TO_BUILD:
            tf.add(ROOT / "configs" / f"champsim_{cfg}.json", arcname=f"configs/champsim_{cfg}.json")
    return out_path


REMOTE_BUILD_AND_RUN = r"""#!/usr/bin/env bash
set -euo pipefail
WORK="$1"
MAX_JOBS="$2"
mkdir -p "$WORK"
cd "$WORK"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

if [ ! -x "$WORK/ChampSim/bin/champsim_mpppb_mdpp_spp" ]; then
  $SUDO apt-get update -qq
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    build-essential cmake curl python3 liblzma-dev zlib1g-dev libbz2-dev libfmt-dev \
    libcli11-dev nlohmann-json3-dev xz-utils >/dev/null
  tar xzf "$WORK/champsim_payload.tar.gz" -C "$WORK"
  cd "$WORK/ChampSim"
  find . -name '*.o' -o -name '*.d' -delete || true
  mkdir -p vcpkg_installed/x64-linux/include traces results
  ln -sfn /usr/lib/x86_64-linux-gnu vcpkg_installed/x64-linux/lib
  sed -i 's/-lCLI11 -llzma -lz -lbz2 -lfmt/-llzma -lz -lbz2 -lfmt/' Makefile
  for cfg in lru_pref ship_pref mpppb_mdpp_pref lru_spp ship_spp mpppb_mdpp_spp; do
    echo "[build] $cfg"
    python3 ./config.sh --replacement-dir "$WORK/champsim_modules" "$WORK/configs/champsim_${cfg}.json" >/dev/null
    make -j"$MAX_JOBS" >/dev/null
  done
fi
ls -l "$WORK"/ChampSim/bin/champsim_*
echo "BUILD_READY"
"""

REMOTE_RUNNER_TEMPLATE = r"""#!/usr/bin/env bash
set -u
WORK="{work}"
MAX_JOBS="{max_jobs}"
cd "$WORK/ChampSim"
mkdir -p "$WORK/results"

run_job() {{
  local grp="$1" pol="$2" bin="$3" prof="$4" tr="$5" w="$6" i="$7"
  local outdir="$WORK/results/$grp/$pol"
  mkdir -p "$outdir"
  local json="$outdir/$tr.json"
  if [ -s "$json" ] || pgrep -f -- "--json $json " >/dev/null 2>&1; then
    echo "skip $grp/$pol/$tr"
    return 0
  fi
  echo "start $grp/$pol/$tr $(date -u +%H:%M:%S)"
  local start
  start=$(date +%s)
  if [ "$prof" != "none" ]; then
    MPPPB_PROFILE="$prof" MPPPB_STATS=1 "bin/$bin" -w "$w" -i "$i" --hide-heartbeat \
      --json "$json" "$WORK/ChampSim/traces/$tr.champsimtrace.xz" \
      > "$outdir/$tr.log" 2> "$outdir/$tr.err"
  else
    "bin/$bin" -w "$w" -i "$i" --hide-heartbeat \
      --json "$json" "$WORK/ChampSim/traces/$tr.champsimtrace.xz" \
      > "$outdir/$tr.log" 2> "$outdir/$tr.err"
  fi
  local rc=$?
  local elapsed=$(( $(date +%s) - start ))
  if [ "$rc" -ne 0 ]; then
    rm -f "$json"
  fi
  echo "elapsed_sec=$elapsed rc=$rc" > "$outdir/$tr.time"
  echo "done $grp/$pol/$tr rc=$rc ${{elapsed}}s"
}}

while IFS='|' read -r grp pol bin prof tr w i; do
  [ -z "$grp" ] && continue
  local_json="$WORK/results/$grp/$pol/$tr.json"
  if [ -s "$local_json" ] || pgrep -f -- "--json $local_json " >/dev/null 2>&1; then
    continue
  fi
  while (( $(ps -eo comm | grep -c '^champsim' || true) >= MAX_JOBS )); do
    sleep 5
  done
  run_job "$grp" "$pol" "$bin" "$prof" "$tr" "$w" "$i" &
  sleep 1
done < "$WORK/tasks.tsv"
wait
echo "ALL_DONE"
"""


def _tasks_tsv(node: NodeSlot) -> str:
    # Sort longest traces first inside each box to minimize multi-wave tail
    ordered = sorted(node.jobs, key=lambda j: j.trace.est_sec, reverse=True)
    return "\n".join(
        f"{j.group}|{j.pol}|{j.binary}|{j.profile or 'none'}|{j.trace.name}|{j.trace.warmup}|{j.trace.sim}"
        for j in ordered
    ) + "\n"


def _ib_cmd(*args: str, stdin_bytes: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
    last = None
    for attempt in range(5):
        p = subprocess.run([INSTABOX_EXE, *args], input=stdin_bytes, capture_output=True)
        last = p
        if p.returncode == 0:
            return p
        err = p.stderr.decode("utf-8", "ignore")
        if ("pending-ops.json" in err or "used by another process" in err) and attempt < 4:
            time.sleep(0.6 * (attempt + 1))
            continue
        break
    assert last is not None
    if check and last.returncode != 0:
        raise RuntimeError(f"instabox {' '.join(args)} failed rc={last.returncode}: {last.stderr.decode('utf-8', 'ignore')[:300]}")
    return last


def _ensure_instabox(node: NodeSlot, ssh_cfg_dir: pathlib.Path) -> pathlib.Path:
    with _IB_META_LOCK:
        existing = _ib_cmd("ls", "--json", check=False).stdout.decode("utf-8", "ignore")
        if f'"{node.name}"' not in existing:
            _ib_cmd("create", "--name", node.name)
        else:
            _ib_cmd("wake", node.name, check=False)
        cfg_txt = _ib_cmd("ssh-config", node.name).stdout.decode("utf-8", "ignore")
    cfg_path = ssh_cfg_dir / f"ssh_{node.name}.cfg"
    cfg_path.write_text(cfg_txt, encoding="utf-8")
    return cfg_path


def _setup_instabox(node: NodeSlot, payload: pathlib.Path, ssh_cfg_dir: pathlib.Path) -> None:
    work = "/data/home/gen3"
    host = f"instabox-{node.name}"
    ssh_cfg = _ensure_instabox(node, ssh_cfg_dir)
    payload_b64 = base64.b64encode(payload.read_bytes())
    _ib_cmd("exec", node.name, "--timeout", "120", "--stdin", "--", f"mkdir -p {work} && base64 -d > {work}/champsim_payload.tar.gz", stdin_bytes=payload_b64)
    out = _ib_cmd("exec", node.name, "--timeout", "600", "--stdin", "--", "bash", "-s", "--", work, str(node.vcpus), stdin_bytes=REMOTE_BUILD_AND_RUN.encode()).stdout.decode("utf-8", "ignore")
    if "BUILD_READY" not in out:
        raise RuntimeError(f"[{node.name}] build failed:\n{out[-800:]}")
    print(f"[{node.name}] ChampSim 6 binaries built", flush=True)

    # Try fast datacenter fetch first (curl for DPC-3, HTTP-Range helper for Zenodo), fallback to scp
    dpc_names = [f"{n}.champsimtrace.xz" for n, t in node.traces.items() if t.suite in ("spec2006", "dpc3_6xx")]
    zen_names = [f"{n}.champsimtrace.xz" for n, t in node.traces.items() if t.suite not in ("spec2006", "dpc3_6xx")]
    fetch_cmds = [f"mkdir -p {work}/ChampSim/traces"]
    if dpc_names:
        base = "https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu"
        for fn in dpc_names:
            dst = f"{work}/ChampSim/traces/{fn}"
            fetch_cmds.append(f"( [ -s '{dst}' ] || curl -sL --retry 3 --max-time 500 -o '{dst}' '{base}/{fn}' ) &")
        fetch_cmds.append("wait")
    if zen_names:
        args_str = " ".join(shlex.quote(fn) for fn in zen_names)
        fetch_cmds.append(f"python3 {work}/scripts/get_ext_traces.py --out {work}/ChampSim/traces --files {args_str} || true")
    _ib_cmd("exec", node.name, "--timeout", "600", "--stdin", "--", "bash", "-s", stdin_bytes=("\n".join(fetch_cmds) + "\n").encode(), check=False)

    for tr_name, tr in node.traces.items():
        local = ROOT / tr.folder / f"{tr_name}.champsimtrace.xz"
        remote = f"{work}/ChampSim/traces/{tr_name}.champsimtrace.xz"
        want = str(local.stat().st_size)
        chk = _ib_cmd("exec", node.name, "--", f"stat -c %s {remote} 2>/dev/null || echo 0", check=False).stdout.decode().strip()
        if chk != want:
            print(f"[{node.name}] fallback scp upload {tr_name} ({tr.mb:.1f} MB)", flush=True)
            subprocess.run(["scp", "-q", "-o", "StrictHostKeyChecking=no", "-F", str(ssh_cfg), str(local), f"{host}:{remote}"], check=True)
        else:
            print(f"[{node.name}] trace ready: {tr_name} ({tr.mb:.1f} MB)", flush=True)

    _ib_cmd("exec", node.name, "--stdin", "--", f"cat > {work}/tasks.tsv", stdin_bytes=_tasks_tsv(node).encode())
    runner = REMOTE_RUNNER_TEMPLATE.format(work=work, max_jobs=node.vcpus)
    _ib_cmd("exec", node.name, "--stdin", "--", f"cat > {work}/run_box.sh && chmod +x {work}/run_box.sh", stdin_bytes=runner.encode())
    _ib_cmd("exec", node.name, "--", f"pgrep -f '{work}/run_box.sh' >/dev/null || (nohup setsid bash {work}/run_box.sh < /dev/null > {work}/run_box.log 2>&1 & echo LAUNCHED)")


def _load_daytona_keys() -> dict[int, str]:
    pairs = dict(l.strip().split("=", 1) for l in DAYTONA_ENV.read_text().splitlines() if l.strip() and "=" in l)
    return {i: pairs[f"DAYTONA_API_KEY_{i}"] for i in (1, 2, 3)}


def _setup_daytona(node: NodeSlot, api_key: str, payload: pathlib.Path, snapshot: str):
    from daytona import Daytona, DaytonaConfig, CreateSandboxFromSnapshotParams

    client = Daytona(DaytonaConfig(api_key=api_key, api_url=DAYTONA_API, target=DAYTONA_TARGET))
    try:
        sb = client.get(node.name)
    except Exception:
        try:
            sb = client.create(CreateSandboxFromSnapshotParams(name=node.name, snapshot=snapshot, auto_stop_interval=0))
        except Exception:
            sb = client.create(CreateSandboxFromSnapshotParams(name=node.name, snapshot="daytona-medium", auto_stop_interval=0))
    home = sb.process.exec("cd ~ && pwd", timeout=30).result.strip().splitlines()[-1]
    work = f"{home}/gen3"
    sb.process.exec(f"mkdir -p {work}/ChampSim/traces", timeout=30)
    sb.fs.upload_file(str(payload), "gen3/champsim_payload.tar.gz", timeout=600)
    build_b64 = base64.b64encode(REMOTE_BUILD_AND_RUN.encode()).decode()
    b_resp = sb.process.exec(f"echo '{build_b64}' | base64 -d > {work}/build.sh && bash {work}/build.sh {work} {node.vcpus}", timeout=1800)
    if "BUILD_READY" not in getattr(b_resp, "result", ""):
        raise RuntimeError(f"[{node.name}] Daytona build failed:\n{getattr(b_resp, 'result', '')[-800:]}")
    print(f"[{node.name}] ChampSim 6 binaries built", flush=True)

    # Try Zenodo HTTP-Range fetch inside Daytona only for missing traces, then upload any remaining/DPC-3 from local
    missing_zen = []
    for tr_name, tr in node.traces.items():
        if tr.suite in ("spec2006", "dpc3_6xx"):
            continue
        local = ROOT / tr.folder / f"{tr_name}.champsimtrace.xz"
        want = str(local.stat().st_size)
        sz = sb.process.exec(f"stat -c %s {work}/ChampSim/traces/{tr_name}.champsimtrace.xz 2>/dev/null || echo 0", timeout=30).result.strip().splitlines()[-1]
        if sz != want:
            missing_zen.append(f"{tr_name}.champsimtrace.xz")
    if missing_zen:
        args_str = " ".join(shlex.quote(fn) for fn in missing_zen)
        sb.process.exec(f"python3 {work}/scripts/get_ext_traces.py --out {work}/ChampSim/traces --files {args_str} || true", timeout=900)

    for tr_name, tr in node.traces.items():
        local = ROOT / tr.folder / f"{tr_name}.champsimtrace.xz"
        remote_rel = f"gen3/ChampSim/traces/{tr_name}.champsimtrace.xz"
        want = str(local.stat().st_size)
        sz = sb.process.exec(f"stat -c %s {work}/ChampSim/traces/{tr_name}.champsimtrace.xz 2>/dev/null || echo 0", timeout=30).result.strip().splitlines()[-1]
        if sz != want:
            print(f"[{node.name}] upload {tr_name} ({tr.mb:.1f} MB)", flush=True)
            sb.fs.upload_file(str(local), remote_rel, timeout=1800)
        else:
            print(f"[{node.name}] trace ready: {tr_name} ({tr.mb:.1f} MB)", flush=True)

    tsv_b64 = base64.b64encode(_tasks_tsv(node).encode()).decode()
    run_b64 = base64.b64encode(REMOTE_RUNNER_TEMPLATE.format(work=work, max_jobs=node.vcpus).encode()).decode()
    sb.process.exec(
        f"pgrep -f '{work}/run_box.sh' >/dev/null && echo ALREADY_RUNNING || ("
        f"echo '{tsv_b64}' | base64 -d > {work}/tasks.tsv && "
        f"echo '{run_b64}' | base64 -d > {work}/run_box.sh && chmod +x {work}/run_box.sh && "
        f"nohup setsid bash {work}/run_box.sh < /dev/null > {work}/run_box.log 2>&1 & echo LAUNCHED)",
        timeout=60,
    )
    return client, sb, work


def _extract_tar_bytes(raw: bytes) -> None:
    out_raw = ROOT / "results" / "raw"
    out_raw.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        tf.extractall(out_raw)


def _pull_instabox(node: NodeSlot) -> tuple[int, int]:
    work = "/data/home/gen3"
    _ib_cmd("wake", node.name, check=False)
    st = _ib_cmd("exec", node.name, "--timeout", "120", "--", f"echo done=$(find {work}/results -name '*.json' 2>/dev/null | wc -l) procs=$(ps -eo comm | grep -c '^champsim' || true)").stdout.decode()
    b64 = _ib_cmd("exec", node.name, "--timeout", "300", "--", f"cd {work}/results && tar czf - . 2>/dev/null | base64 -w0").stdout.decode().strip()
    if b64:
        _extract_tar_bytes(base64.b64decode(b64))
    done = int(st.split("done=")[1].split()[0])
    procs = int(st.split("procs=")[1].split()[0])
    return done, procs


def _pull_daytona(node: NodeSlot, sb, work: str) -> tuple[int, int]:
    st = sb.process.exec(f"echo done=$(find {work}/results -name '*.json' 2>/dev/null | wc -l) procs=$(ps -eo comm | grep -c '^champsim' || true)", timeout=60).result
    b64 = sb.process.exec(f"cd {work}/results && tar czf - . 2>/dev/null | base64 -w0", timeout=300).result.strip()
    if b64:
        _extract_tar_bytes(base64.b64decode(b64))
    done = int(st.split("done=")[1].split()[0])
    procs = int(st.split("procs=")[1].split()[0])
    return done, procs


def verify_group_outputs(selected: list[str]) -> bool:
    group_defs = {"1": ("g1_old_spp", OLD_TRACES), "2": ("g2_new_pref", NEW_TRACES), "3": ("g3_new_spp", NEW_TRACES)}
    ok = True
    for g_key in selected:
        g_name, tr_list = group_defs[g_key]
        bad = []
        for pol, _, _ in GROUP_POLICIES[g_name]:
            for tr in tr_list:
                p = ROOT / "results" / "raw" / g_name / pol / f"{tr.name}.json"
                if not p.exists():
                    bad.append(("missing", pol, tr.name))
                    continue
                try:
                    sim = json.loads(p.read_text())[0]["sim"]
                    ins = sim["cores"][0]["instructions"]
                    cyc = sim["cores"][0]["cycles"]
                    if not (tr.sim <= ins <= tr.sim + 50) or cyc <= 0:
                        bad.append(("window", pol, tr.name, ins, cyc))
                except Exception as exc:
                    bad.append(("json", pol, tr.name, str(exc)))
        print(f"[verify] {g_name}: bad={bad if bad else 'NONE'}")
        if bad:
            ok = False
    return ok


def print_plan(nodes: list[NodeSlot]) -> None:
    total_jobs = sum(len(n.jobs) for n in nodes)
    total_vcpus = sum(n.vcpus for n in nodes)
    max_wall = 0.0
    print(f"\n=== 3-Group Cloud Shard Plan ({total_jobs} pending runs across {len(nodes)} VMs, {total_vcpus} vCPUs) ===")
    for n in nodes:
        wall_min = (n.est_cpu_sec / n.vcpus + (n.trace_mb / 5.0 if n.provider == "daytona" else n.trace_mb / 40.0)) / 60.0
        max_wall = max(max_wall, wall_min)
        tr_list = ", ".join(sorted(n.traces))
        print(f"  {n.name:9s} ({n.provider:8s} {n.vcpus} vCPU): {len(n.jobs):3d} runs, {len(n.traces):2d} traces ({n.trace_mb:6.1f} MB), est ~{wall_min:5.1f} min | {tr_list}")
    print(f"Estimated simulation makespan (after ~3m VM build/upload): ~{max_wall:.1f} min ({max_wall / 60:.2f} h)\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=("all", "1", "2", "3"), default="all")
    ap.add_argument("--daytona-snapshot", choices=("daytona-large", "daytona-medium"), default="daytona-large")
    ap.add_argument("--plan", action="store_true", help="Print shard assignment & runtime estimate without launching VMs")
    ap.add_argument("--cleanup", action="store_true", help="Delete cloud sandboxes after all results verify")
    args = ap.parse_args()

    selected = ["1", "2", "3"] if args.group == "all" else [args.group]
    bundles = collect_trace_bundles(selected, skip_existing=True)
    dt_cpus = 4 if args.daytona_snapshot == "daytona-large" else 2
    dt_disk = 1800 if args.daytona_snapshot == "daytona-large" else 1100
    nodes = assign_shards(bundles, daytona_vcpus=dt_cpus, daytona_disk_cap_mb=dt_disk)
    print_plan(nodes)
    if args.plan:
        return 0

    for n in nodes:
        for tr_name, tr in n.traces.items():
            p = ROOT / tr.folder / f"{tr_name}.champsimtrace.xz"
            if not p.exists():
                raise FileNotFoundError(f"Missing local trace: {p} (run scripts/get_ext_traces.py first)")

    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="champsim_gen3_"))
    payload = build_payload_tarball(tmp_dir / "champsim_payload.tar.gz")
    print(f"Packed payload: {payload.stat().st_size / 1048576:.2f} MB", flush=True)

    dt_keys = _load_daytona_keys()
    active_nodes = [n for n in nodes if n.jobs]
    dt_handles = {}

    with ThreadPoolExecutor(max_workers=len(active_nodes)) as ex:
        futs = {}
        for n in active_nodes:
            if n.provider == "instabox":
                futs[ex.submit(_setup_instabox, n, payload, tmp_dir)] = n
            else:
                futs[ex.submit(_setup_daytona, n, dt_keys[n.index], payload, args.daytona_snapshot)] = n
        for fut in as_completed(futs):
            n = futs[fut]
            res = fut.result()
            if n.provider == "daytona":
                dt_handles[n.name] = res
            print(f"[{n.name}] setup + launch complete ({len(n.jobs)} runs)", flush=True)

    expect_total = sum(len(n.jobs) for n in active_nodes)
    zero_busy_cycles = 0
    while True:
        time.sleep(120)
        done_sum = 0
        busy_sum = 0
        for n in active_nodes:
            try:
                if n.provider == "instabox":
                    d, b = _pull_instabox(n)
                else:
                    _, sb, work = dt_handles[n.name]
                    d, b = _pull_daytona(n, sb, work)
                done_sum += d
                busy_sum += b
            except Exception as exc:
                print(f"[{n.name}] poll warn: {exc}", flush=True)
                busy_sum += 1
        print(f"[progress] {done_sum}/{expect_total} done, {busy_sum} procs running", flush=True)
        if busy_sum == 0:
            zero_busy_cycles += 1
            if done_sum >= expect_total or zero_busy_cycles >= 3:
                break
        else:
            zero_busy_cycles = 0

    for g_key in selected:
        g_name = {"1": "g1_old_spp", "2": "g2_new_pref", "3": "g3_new_spp"}[g_key]
        raw_dir = ROOT / "results" / "raw" / g_name
        csv_out = ROOT / "results" / f"{g_name}.csv"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "summarize_champsim.py"), str(raw_dir), str(csv_out)], check=True)

    all_ok = verify_group_outputs(selected)
    if args.cleanup and all_ok:
        for n in active_nodes:
            if n.provider == "instabox":
                _ib_cmd("rm", n.name, check=False)
            else:
                client, sb, _ = dt_handles[n.name]
                client.delete(sb)
    print("ALL 3 GROUPS COMPLETE" if all_ok else "COMPLETED WITH VERIFICATION ERRORS", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
