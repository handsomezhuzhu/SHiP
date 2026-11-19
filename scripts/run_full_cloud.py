#!/usr/bin/env python3
"""Orchestrate the dual-prefetcher completion & full 28-trace LOO ablations on cloud VMs.

Uses all 5 Instabox sandboxes (4 vCPU, 8 GiB, 20 GiB disk) + all 3 Daytona accounts
(daytona-large: 4 vCPU, 8 GiB, 10 GiB disk) = 32 parallel vCPU across 8 VMs.

Experiment groups covered (all single-core, unified configs):
  1. g_new_nopref : 20 new traces x {lru, ship, mpppb(author1), ta_mpppb_np} = 80 runs
  2. loo_pref     : 28 traces x {no_zeropc, no_ptw_prot, no_write_arb, no_pref_arb} + 22 missing tduel = 134 runs
                    (6 existing SPEC06 tduel JSONs in results/raw/v3_ablate/v3_c21_tduel are verified & synced)
  3. loo_spp      : 28 traces x {no_zeropc, no_ptw_prot, no_write_arb, no_pref_arb, tduel} = 140 runs

Usage:
  python scripts/run_full_cloud.py --plan
  python scripts/run_full_cloud.py --yes
"""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import io
import json
import os
import pathlib
import posixpath
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig  # noqa: E402
from run_3groups_cloud import (  # noqa: E402
    DAYTONA_API,
    DAYTONA_ENV,
    DAYTONA_TARGET,
    INSTABOX_EXE,
    NEW_TRACES,
    OLD_TRACES,
    TraceMeta,
)

RESULTS_RAW = ROOT / "results" / "raw"
STATE_LOG = ROOT / "results" / "logs" / "run_full_cloud_status.json"
V3_TDUEL_DIR = RESULTS_RAW / "v3_ablate" / "v3_c21_tduel"
PRINT_LOCK = threading.Lock()
IB_CREATE_LOCK = threading.Lock()
IB_CREATE_TIMES: list[float] = []


def log(msg: str) -> None:
    with PRINT_LOCK:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    group: str
    variant: str
    config_name: str
    binary: str
    trace: TraceMeta
    trace_subdir: str  # "traces" or "traces_new"
    out_json: pathlib.Path
    env_vars: dict[str, str]
    est_sec: int

    @property
    def rel_out(self) -> str:
        return f"{self.group}/{self.variant}/{self.trace.name}.json"


@dataclass
class NodeSlot:
    name: str
    provider: str  # "instabox" or "daytona"
    max_jobs: int = 4
    cap_mb: float = 12000.0
    api_key: str = ""
    snapshot: str = "daytona-large"
    jobs: list[JobSpec] = field(default_factory=list)
    traces_mb: float = 0.0
    est_cpu_sec: float = 0.0
    trace_names: set[str] = field(default_factory=set)

    @property
    def est_wall_sec(self) -> float:
        return self.est_cpu_sec / max(1, self.max_jobs)


def load_daytona_keys() -> list[str]:
    keys: list[str] = []
    if not DAYTONA_ENV.exists():
        return keys
    for line in DAYTONA_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip().startswith("DAYTONA_API_KEY") and v.strip():
            keys.append(v.strip())
    return keys


def existing_json_ok(path: pathlib.Path, expected_sim: int) -> bool:
    if not path.exists() or path.stat().st_size < 200:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        roi = data[0]["roi"]
        core = roi["cores"][0]
        inst = int(core["instructions"])
        cyc = int(core["cycles"])
        llc = roi["LLC"]
        _ = int(llc["LOAD"]["miss"][0])
        return (expected_sim <= inst <= expected_sim + 100) and cyc > 0
    except Exception:
        return False


def sync_existing_tduel() -> int:
    """Copy already-verified SPEC06 tduel JSONs from v3_c21_tduel into loo_pref/tduel."""
    dst_dir = RESULTS_RAW / "loo_pref" / "tduel"
    dst_dir.mkdir(parents=True, exist_ok=True)
    trace_map = {t.name: t for t in OLD_TRACES}
    synced = 0
    if not V3_TDUEL_DIR.exists():
        return 0
    for src in sorted(V3_TDUEL_DIR.glob("*.json")):
        tm = trace_map.get(src.stem)
        if tm is None or not existing_json_ok(src, tm.sim):
            continue
        dst = dst_dir / src.name
        if not existing_json_ok(dst, tm.sim):
            shutil.copy2(src, dst)
            synced += 1
    return synced


def build_all_jobs(only_groups: set[str] | None = None) -> tuple[list[JobSpec], int]:
    sync_existing_tduel()
    all_specs: list[JobSpec] = []
    skipped = 0

    def maybe_add(
        group: str,
        variant: str,
        config_name: str,
        trace: TraceMeta,
        trace_subdir: str,
        env_vars: dict[str, str],
        weight: float,
    ) -> None:
        nonlocal skipped
        if only_groups is not None and group not in only_groups:
            return
        out_json = RESULTS_RAW / group / variant / f"{trace.name}.json"
        if existing_json_ok(out_json, trace.sim):
            skipped += 1
            return
        jid = f"{group}__{variant}__{trace.name}"
        all_specs.append(
            JobSpec(
                job_id=jid,
                group=group,
                variant=variant,
                config_name=config_name,
                binary=f"champsim_{config_name}",
                trace=trace,
                trace_subdir=trace_subdir,
                out_json=out_json,
                env_vars=dict(env_vars),
                est_sec=max(60, int(trace.est_sec * weight)),
            )
        )

    # Group 1: New 20 traces under No-Pref
    np_variants = [
        ("lru", "lru", {}),
        ("ship", "ship", {}),
        ("mpppb", "mpppb_mdpp", {"MPPPB_PROFILE": "author1"}),
        ("ta_mpppb_np", "mpppb_mdpp", {"MPPPB_PROFILE": "ta_mpppb_np"}),
    ]
    for tr in NEW_TRACES:
        for var, cfg, env in np_variants:
            maybe_add("g_new_nopref", var, cfg, tr, "traces_new", env, 0.75)

    # Groups 2 & 3: Full 28-trace LOO + tduel across ip_stride & spp_dev
    loo_variants = [
        ("no_zeropc", {"MPPPB_PROFILE": "ta_mpppb", "MPPPB_LOO": "no_zero_pc"}),
        ("no_ptw_prot", {"MPPPB_PROFILE": "ta_mpppb", "MPPPB_LOO": "no_ptw_prot"}),
        ("no_write_arb", {"MPPPB_PROFILE": "ta_mpppb", "MPPPB_LOO": "no_write_arb"}),
        ("no_pref_arb", {"MPPPB_PROFILE": "ta_mpppb", "MPPPB_LOO": "no_pref_arb"}),
        ("tduel", {"MPPPB_PROFILE": "ta_mpppb", "MPPPB_TRANS_DUEL": "1"}),
    ]
    all_traces = [(t, "traces") for t in OLD_TRACES] + [(t, "traces_new") for t in NEW_TRACES]
    for tr, sub in all_traces:
        for var, env in loo_variants:
            maybe_add("loo_pref", var, "mpppb_mdpp_pref", tr, sub, env, 1.00)
            maybe_add("loo_spp", var, "mpppb_mdpp_spp", tr, sub, env, 1.15)

    return all_specs, skipped


def build_slots(daytona_snapshot: str, daytona_cap_mb: float, use_instabox: bool, use_daytona: bool) -> list[NodeSlot]:
    slots: list[NodeSlot] = []
    if use_instabox:
        for i in range(1, 6):
            slots.append(NodeSlot(name=f"full-ib{i}", provider="instabox", max_jobs=4, cap_mb=12000.0))
    if use_daytona:
        for idx, key in enumerate(load_daytona_keys(), start=1):
            slots.append(
                NodeSlot(
                    name=f"full-dt{idx}",
                    provider="daytona",
                    max_jobs=4,
                    cap_mb=daytona_cap_mb,
                    api_key=key,
                    snapshot=daytona_snapshot,
                )
            )
    return slots


def assign_shards(jobs: list[JobSpec], slots: list[NodeSlot]) -> None:
    if not jobs or not slots:
        return
    # Group by trace so every trace is uploaded only once unless very few traces remain
    by_trace: dict[str, list[JobSpec]] = {}
    for j in jobs:
        by_trace.setdefault(j.trace.name, []).append(j)

    if len(by_trace) >= len(slots):
        bundles = sorted(by_trace.values(), key=lambda js: sum(x.est_sec for x in js), reverse=True)
    else:
        # On partial resumes with <8 remaining traces, split at individual job level
        bundles = [[j] for j in sorted(jobs, key=lambda x: x.est_sec, reverse=True)]

    for b in bundles:
        tr = b[0].trace
        b_sec = sum(x.est_sec for x in b)
        cands = []
        for s in slots:
            extra_mb = 0.0 if tr.name in s.trace_names else tr.mb
            if s.traces_mb + extra_mb <= s.cap_mb:
                cands.append((s.est_wall_sec, extra_mb, s))
        if not cands:
            # Relax cap onto Instabox if needed
            ib_cands = [(s.est_wall_sec, s) for s in slots if s.provider == "instabox"]
            if not ib_cands:
                raise RuntimeError(f"Trace {tr.name} ({tr.mb} MB) exceeds all available node disk caps")
            best = min(ib_cands, key=lambda x: x[0])[1]
        else:
            best = min(cands, key=lambda x: (x[0], x[1]))[2]
        if tr.name not in best.trace_names:
            best.trace_names.add(tr.name)
            best.traces_mb += tr.mb
        best.jobs.extend(b)
        best.est_cpu_sec += b_sec
    for s in slots:
        s.jobs.sort(key=lambda j: -j.est_sec)


def build_payload_tarball(out_path: pathlib.Path) -> pathlib.Path:
    cs = ROOT / "env" / "ChampSim"
    keep_dirs = ("inc", "src", "branch", "btb", "prefetcher", "replacement", "config")
    keep_files = ("Makefile", "config.sh", "champsim_config.json", "global.options", "module.options")
    with tarfile.open(out_path, "w:gz") as tf:
        for d in keep_dirs:
            tf.add(cs / d, arcname=f"ChampSim/{d}", filter=lambda ti: None if ti.name.endswith((".o", ".d")) or "__pycache__" in ti.name else ti)
        for fn in keep_files:
            tf.add(cs / fn, arcname=f"ChampSim/{fn}")
        tf.add(ROOT / "champsim_modules", arcname="champsim_modules", filter=lambda ti: None if "__pycache__" in ti.name else ti)
        for cfg in ["lru", "ship", "mpppb_mdpp", "mpppb_mdpp_pref", "mpppb_mdpp_spp"]:
            p = ROOT / "configs" / f"champsim_{cfg}.json"
            tf.add(p, arcname=f"configs/champsim_{cfg}.json")
    return out_path


# ---- Cloud VM abstraction ----


class CloudVM:
    def __init__(self, slot: NodeSlot):
        self.slot = slot
        self.work_dir = "/data/home/full_run" if slot.provider == "instabox" else "/tmp/full_run"

    def create(self) -> None:
        raise NotImplementedError

    def upload_file(self, local_path: pathlib.Path, remote_path: str) -> None:
        raise NotImplementedError

    def exec_bash(self, script: str, timeout: int = 900) -> str:
        raise NotImplementedError

    def download_bytes(self, remote_path: str) -> bytes:
        raise NotImplementedError

    def delete(self) -> None:
        raise NotImplementedError

    def keep_awake(self) -> None:
        pass


class InstaboxVM(CloudVM):
    def __init__(self, slot: NodeSlot):
        super().__init__(slot)
        self.ssh_host = ""
        self.ssh_port = 2222
        self.ssh_token = ""

    def _ib(self, *args: str, stdin_bytes: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess:
        res = subprocess.run([INSTABOX_EXE, *args], input=stdin_bytes, capture_output=True)
        if check and res.returncode != 0:
            raise RuntimeError(
                f"instabox {' '.join(args)} rc={res.returncode}\n"
                f"OUT: {res.stdout.decode(errors='replace')}\nERR: {res.stderr.decode(errors='replace')}"
            )
        return res

    def create(self) -> None:
        self._ib("rm", self.slot.name, check=False)
        for attempt in range(1, 7):
            with IB_CREATE_LOCK:
                now = time.monotonic()
                IB_CREATE_TIMES[:] = [t for t in IB_CREATE_TIMES if now - t < 68.0]
                if len(IB_CREATE_TIMES) >= 2:
                    wait_s = 68.0 - (now - IB_CREATE_TIMES[0]) + 1.0
                    if wait_s > 0:
                        log(f"[{self.slot.name}] throttling Instabox create for {wait_s:.1f}s (3/min limit)...")
                        time.sleep(wait_s)
                IB_CREATE_TIMES.append(time.monotonic())
            res = self._ib("create", "--name", self.slot.name, check=False)
            if res.returncode == 0:
                break
            err = res.stderr.decode(errors="replace")
            if "rate_limited" in err and attempt < 6:
                log(f"[{self.slot.name}] hit Instabox create rate limit (attempt {attempt}), backing off 35s...")
                time.sleep(35)
                continue
            raise RuntimeError(
                f"instabox create --name {self.slot.name} rc={res.returncode}\n"
                f"OUT: {res.stdout.decode(errors='replace')}\nERR: {err}"
            )
        res = self._ib("ssh-token", self.slot.name, "--json")
        info = json.loads(res.stdout.decode("utf-8"))
        self.ssh_host = info["host"]
        self.ssh_port = int(info.get("port", 2222))
        self.ssh_token = info["token"]

    def _ssh_cmd(self, remote_cmd: str) -> list[str]:
        return [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "LogLevel=ERROR",
            "-p", str(self.ssh_port),
            f"{self.ssh_token}@{self.ssh_host}",
            remote_cmd,
        ]

    def keep_awake(self) -> None:
        try:
            res = self._ib("get", self.slot.name, "--json", check=False)
            if res.returncode == 0:
                st = json.loads(res.stdout.decode("utf-8")).get("state", "").lower()
                if st in {"paused", "suspended"}:
                    log(f"[{self.slot.name}] waking paused Instabox sandbox...")
                    self._ib("wake", self.slot.name, check=False)
        except Exception:
            pass

    def upload_file(self, local_path: pathlib.Path, remote_path: str) -> None:
        parent = posixpath.dirname(remote_path)
        remote_cmd = f"mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(remote_path)}"
        for attempt in range(1, 4):
            self.keep_awake()
            with local_path.open("rb") as f:
                res = subprocess.run(self._ssh_cmd(remote_cmd), stdin=f, capture_output=True, timeout=3600)
            if res.returncode == 0:
                return
            log(f"[{self.slot.name}] upload attempt {attempt} failed for {local_path.name}: {res.stderr.decode(errors='replace')}")
            time.sleep(3 * attempt)
        raise RuntimeError(f"[{self.slot.name}] failed to upload {local_path}")

    def exec_bash(self, script: str, timeout: int = 600) -> str:
        clamped = max(1, min(int(timeout), 600))
        for attempt in range(1, 3):
            self.keep_awake()
            try:
                res = self._ib(
                    "exec",
                    self.slot.name,
                    "--timeout",
                    str(clamped),
                    "--stdin",
                    "--",
                    "bash -s",
                    stdin_bytes=script.encode("utf-8"),
                )
                return res.stdout.decode("utf-8", errors="replace")
            except Exception as e:
                if attempt == 2:
                    raise
                log(f"[{self.slot.name}] exec retry after error: {e}")
                time.sleep(3)
        return ""

    def download_bytes(self, remote_path: str) -> bytes:
        for attempt in range(1, 4):
            self.keep_awake()
            res = subprocess.run(
                self._ssh_cmd(f"cat {shlex.quote(remote_path)}"),
                capture_output=True,
                timeout=900,
            )
            if res.returncode == 0:
                return res.stdout
            time.sleep(2 * attempt)
        raise RuntimeError(f"[{self.slot.name}] failed to download {remote_path}")

    def delete(self) -> None:
        self._ib("rm", self.slot.name, check=False)


class DaytonaVM(CloudVM):
    def __init__(self, slot: NodeSlot):
        super().__init__(slot)
        self.client = Daytona(DaytonaConfig(api_key=slot.api_key, api_url=DAYTONA_API, target=DAYTONA_TARGET))
        self.sb = None

    def create(self) -> None:
        items = list(getattr(self.client.list(), "items", self.client.list()))
        for old in items:
            if getattr(old, "name", "") == self.slot.name or True:
                self.client.delete(old)
        self.sb = self.client.create(
            CreateSandboxFromSnapshotParams(snapshot=self.slot.snapshot, auto_stop_interval=0),
            timeout=180,
        )

    def upload_file(self, local_path: pathlib.Path, remote_path: str) -> None:
        assert self.sb is not None
        parent = posixpath.dirname(remote_path)
        self.sb.process.exec(f"mkdir -p {shlex.quote(parent)}", timeout=60)
        for attempt in range(1, 4):
            try:
                self.sb.fs.upload_file(str(local_path), remote_path, timeout=3600)
                return
            except Exception as e:
                log(f"[{self.slot.name}] Daytona upload attempt {attempt} failed for {local_path.name}: {e}")
                time.sleep(4 * attempt)
        raise RuntimeError(f"[{self.slot.name}] Daytona failed to upload {local_path}")

    def exec_bash(self, script: str, timeout: int = 900) -> str:
        assert self.sb is not None
        b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
        cmd = f"bash -lc 'echo {shlex.quote(b64)} | base64 -d | bash -s'"
        res = self.sb.process.exec(cmd, timeout=timeout)
        if res.exit_code != 0:
            raise RuntimeError(f"[{self.slot.name}] Daytona exec rc={res.exit_code}\n{res.result}")
        return res.result or ""

    def download_bytes(self, remote_path: str) -> bytes:
        assert self.sb is not None
        for attempt in range(1, 4):
            try:
                data = self.sb.fs.download_file(remote_path)
                assert data is not None
                return data
            except Exception as e:
                if attempt == 3:
                    raise RuntimeError(f"[{self.slot.name}] Daytona download failed: {e}") from e
                time.sleep(2 * attempt)
        return b""

    def delete(self) -> None:
        if self.sb is not None:
            try:
                self.client.delete(self.sb)
            except Exception:
                pass
            self.sb = None


def make_vm(slot: NodeSlot) -> CloudVM:
    return InstaboxVM(slot) if slot.provider == "instabox" else DaytonaVM(slot)


def make_worker_script(work_dir: str, max_jobs: int) -> str:
    return f"""#!/usr/bin/env bash
set -uo pipefail
WORK={shlex.quote(work_dir)}
BIN_DIR="$WORK/ChampSim/bin"
TR_DIR="$WORK/traces"
OUT_DIR="$WORK/out"
ERR_DIR="$WORK/err"
TASKS="$WORK/tasks.tsv"
PROG="$WORK/progress.log"
STATUS="$WORK/STATUS"
MAX_JOBS={max_jobs}

mkdir -p "$OUT_DIR" "$ERR_DIR"
: > "$PROG"
echo "RUNNING" > "$STATUS"

run_one() {{
  local jid="$1" grp="$2" var="$3" bin="$4" tr="$5" warm="$6" sim="$7" env_b64="$8"
  local rel="${{grp}}/${{var}}/${{tr}}.json"
  local final="$OUT_DIR/$rel"
  local tmp="${{final}}.tmp"
  local err="$ERR_DIR/${{jid}}.err"
  local tr_path="$TR_DIR/${{tr}}.champsimtrace.xz"
  mkdir -p "$(dirname "$final")"

  local env_str=""
  if [ -n "$env_b64" ] && [ "$env_b64" != "-" ]; then
    env_str=$(printf '%s' "$env_b64" | base64 -d)
  fi

  local t0 t1 elapsed rc=0
  t0=$(date +%s)
  if [ -n "$env_str" ]; then
    # shellcheck disable=SC2086
    env $env_str "$BIN_DIR/$bin" -w "$warm" -i "$sim" --hide-heartbeat --json "$tmp" "$tr_path" >/dev/null 2>"$err" || rc=$?
  else
    "$BIN_DIR/$bin" -w "$warm" -i "$sim" --hide-heartbeat --json "$tmp" "$tr_path" >/dev/null 2>"$err" || rc=$?
  fi
  t1=$(date +%s)
  elapsed=$((t1 - t0))

  if [ "$rc" -eq 0 ] && [ -s "$tmp" ] && python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert int(d[0]['roi']['cores'][0]['instructions']) >= int(sys.argv[2])" "$tmp" "$sim" 2>/dev/null; then
    mv -f "$tmp" "$final"
    echo "OK|${{jid}}|${{elapsed}}|${{rel}}" >> "$PROG"
  else
    rm -f "$tmp"
    echo "FAIL|${{jid}}|${{rc}}|${{elapsed}}|${{rel}}" >> "$PROG"
  fi
}}

while IFS=$'\\t' read -r jid grp var bin tr warm sim env_b64; do
  [ -z "$jid" ] && continue
  while [ "$(jobs -rp | wc -l)" -ge "$MAX_JOBS" ]; do
    sleep 2
  done
  run_one "$jid" "$grp" "$var" "$bin" "$tr" "$warm" "$sim" "$env_b64" &
done < "$TASKS"

wait
echo "ALL_DONE" > "$STATUS"
"""


def make_prepare_script(work_dir: str) -> str:
    return f"""set -euo pipefail
WORK={shlex.quote(work_dir)}
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
$SUDO apt-get update -qq || (sleep 5 && $SUDO apt-get update -qq)
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \\
  build-essential cmake curl python3 liblzma-dev zlib1g-dev libbz2-dev libfmt-dev \\
  libcli11-dev nlohmann-json3-dev xz-utils >/dev/null
rm -rf "$WORK/ChampSim" "$WORK/champsim_modules" "$WORK/configs"
tar xzf "$WORK/champsim_payload.tar.gz" -C "$WORK"
rm -f "$WORK/champsim_payload.tar.gz"
$SUDO apt-get clean >/dev/null 2>&1 || true

cd "$WORK/ChampSim"
mkdir -p vcpkg_installed/x64-linux/include
ln -sfn /usr/lib/x86_64-linux-gnu vcpkg_installed/x64-linux/lib
sed -i 's/-lCLI11 -llzma -lz -lbz2 -lfmt/-llzma -lz -lbz2 -lfmt/' Makefile
"""


def serialize_tasks_tsv(jobs: list[JobSpec]) -> str:
    lines: list[str] = []
    for j in jobs:
        if j.env_vars:
            env_str = " ".join(f"{k}={v}" for k, v in sorted(j.env_vars.items()))
            env_b64 = base64.b64encode(env_str.encode("utf-8")).decode("ascii")
        else:
            env_b64 = "-"
        lines.append(
            "\t".join(
                [
                    j.job_id,
                    j.group,
                    j.variant,
                    j.binary,
                    j.trace.name,
                    str(j.trace.warmup),
                    str(j.trace.sim),
                    env_b64,
                ]
            )
        )
    return "\n".join(lines) + "\n"


def pull_new_jsons(vm: CloudVM, shard_jobs: list[JobSpec], pulled: set[str]) -> tuple[int, list[str]]:
    """Tar completed JSON files not yet verified locally and extract them cleanly."""
    pending_map = {j.rel_out: j for j in shard_jobs if j.rel_out not in pulled}
    if not pending_map:
        return 0, []
    out = vm.exec_bash(
        f"""WORK={shlex.quote(vm.work_dir)}
cd "$WORK/out" 2>/dev/null || exit 0
find . -type f -name '*.json' ! -name '*.tmp' | sed 's|^\\./||' | sort
""",
        timeout=120,
    )
    ready = [ln.strip() for ln in out.splitlines() if ln.strip() in pending_map]
    if not ready:
        return 0, []

    flist_b64 = base64.b64encode(("\n".join(ready) + "\n").encode("utf-8")).decode("ascii")
    vm.exec_bash(
        f"""WORK={shlex.quote(vm.work_dir)}
cd "$WORK/out"
echo {shlex.quote(flist_b64)} | base64 -d > /tmp/pull_list.txt
tar -czf /tmp/pull_ready.tar.gz -T /tmp/pull_list.txt
""",
        timeout=300,
    )
    raw_tar = vm.download_bytes("/tmp/pull_ready.tar.gz")
    vm.exec_bash("rm -f /tmp/pull_ready.tar.gz /tmp/pull_list.txt", timeout=60)

    newly_ok = 0
    bad_list: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            rel = member.name.removeprefix("./")
            job = pending_map.get(rel)
            if job is None:
                continue
            fobj = tf.extractfile(member)
            if fobj is None:
                continue
            payload = fobj.read()
            job.out_json.parent.mkdir(parents=True, exist_ok=True)
            tmp_local = job.out_json.with_suffix(".json.tmp")
            tmp_local.write_bytes(payload)
            if existing_json_ok(tmp_local, job.trace.sim):
                tmp_local.replace(job.out_json)
                pulled.add(rel)
                newly_ok += 1
            else:
                tmp_local.unlink(missing_ok=True)
                bad_list.append(rel)
    return newly_ok, bad_list


def provision_and_start_node(slot: NodeSlot, payload_tar: pathlib.Path) -> CloudVM:
    vm = make_vm(slot)
    log(f"[{slot.name}] creating {slot.provider} sandbox...")
    vm.create()
    log(f"[{slot.name}] uploading payload + {len(slot.trace_names)} traces ({slot.traces_mb:.1f} MB)...")
    vm.upload_file(payload_tar, f"{vm.work_dir}/champsim_payload.tar.gz")

    uploaded: set[str] = set()
    for j in slot.jobs:
        if j.trace.name in uploaded:
            continue
        local_tr = ROOT / j.trace_subdir / f"{j.trace.name}.champsimtrace.xz"
        vm.upload_file(local_tr, f"{vm.work_dir}/traces/{j.trace.name}.champsimtrace.xz")
        uploaded.add(j.trace.name)

    needed_cfgs = sorted({j.config_name for j in slot.jobs})
    log(f"[{slot.name}] preparing OS deps & unpacking payload...")
    vm.exec_bash(make_prepare_script(vm.work_dir), timeout=600)
    for cfg in needed_cfgs:
        log(f"[{slot.name}] building {cfg}...")
        vm.exec_bash(
            f"""set -euo pipefail
cd {shlex.quote(vm.work_dir)}/ChampSim
find . -name '*.o' -o -name '*.d' -delete || true
python3 ./config.sh --replacement-dir {shlex.quote(vm.work_dir)}/champsim_modules {shlex.quote(vm.work_dir)}/configs/champsim_{shlex.quote(cfg)}.json >/dev/null
make -j{slot.max_jobs} >/dev/null
find . -name '*.o' -o -name '*.d' -delete || true
ls -l bin/champsim_{shlex.quote(cfg)}
""",
            timeout=600,
        )
    vm.exec_bash(f"df -h {shlex.quote(vm.work_dir)}", timeout=60)

    with tempfile.TemporaryDirectory() as td:
        tp = pathlib.Path(td) / "tasks.tsv"
        wp = pathlib.Path(td) / "worker.sh"
        tp.write_text(serialize_tasks_tsv(slot.jobs), encoding="utf-8", newline="\n")
        wp.write_text(make_worker_script(vm.work_dir, slot.max_jobs), encoding="utf-8", newline="\n")
        vm.upload_file(tp, f"{vm.work_dir}/tasks.tsv")
        vm.upload_file(wp, f"{vm.work_dir}/worker.sh")

    vm.exec_bash(
        f"""WORK={shlex.quote(vm.work_dir)}
chmod +x "$WORK/worker.sh"
nohup bash "$WORK/worker.sh" </dev/null >"$WORK/worker.log" 2>&1 &
sleep 1
echo STARTED_PID=$!
""",
        timeout=120,
    )
    log(f"[{slot.name}] launched detached worker ({len(slot.jobs)} jobs, est {slot.est_wall_sec/3600:.2f}h)")
    return vm


def print_plan(slots: list[NodeSlot], total_jobs: int, skipped: int) -> None:
    print(f"Pending jobs: {total_jobs} (already verified & skipped: {skipped})")
    for s in slots:
        cfgs = sorted({j.config_name for j in s.jobs})
        grps = {}
        for j in s.jobs:
            grps[j.group] = grps.get(j.group, 0) + 1
        print(
            f"  {s.name:9s} [{s.provider:8s}] jobs={len(s.jobs):3d} traces={len(s.trace_names):2d} "
            f"mb={s.traces_mb:6.1f}/{s.cap_mb:.0f} est={s.est_wall_sec:5.0f}s ({s.est_wall_sec/3600:.2f}h) "
            f"bins={len(cfgs)} groups={grps}"
        )
    active = [s for s in slots if s.jobs]
    if active:
        print(f"Max est wall: {max(s.est_wall_sec for s in active)/3600:.2f}h, "
              f"Min est wall: {min(s.est_wall_sec for s in active)/3600:.2f}h, "
              f"Total trace upload MB: {sum(s.traces_mb for s in active):.1f}")


def cleanup_all(vms: list[CloudVM]) -> None:
    for vm in vms:
        try:
            vm.delete()
        except Exception as e:
            log(f"[cleanup] {vm.slot.name} delete warning: {e}")
    # Double-check all Daytona accounts (wait briefly for async deletes)
    time.sleep(4)
    for idx, key in enumerate(load_daytona_keys(), start=1):
        try:
            d = Daytona(DaytonaConfig(api_key=key, api_url=DAYTONA_API, target=DAYTONA_TARGET))
            items = list(getattr(d.list(), "items", d.list()))
            for sb in items:
                try:
                    d.delete(sb)
                except Exception:
                    pass
            if items:
                time.sleep(4)
            log(f"[cleanup] daytona key #{idx} remaining={len(list(getattr(d.list(), 'items', d.list())))}")
        except Exception as e:
            log(f"[cleanup] daytona key #{idx} check error: {e}")
    # Double-check Instabox
    try:
        res = subprocess.run([INSTABOX_EXE, "ls", "--json"], capture_output=True)
        if res.returncode == 0:
            rem = [m.get("name") for m in json.loads(res.stdout.decode("utf-8") or "[]")]
            for nm in rem:
                if nm.startswith("full-ib"):
                    subprocess.run([INSTABOX_EXE, "rm", nm], capture_output=True)
            res2 = subprocess.run([INSTABOX_EXE, "ls", "--json"], capture_output=True)
            log(f"[cleanup] instabox remaining={res2.stdout.decode().strip()}")
    except Exception as e:
        log(f"[cleanup] instabox check error: {e}")


def run_fleet(args: argparse.Namespace) -> int:
    only_groups = set(args.groups) if args.groups else None
    jobs, skipped = build_all_jobs(only_groups)
    slots = build_slots(args.daytona_snapshot, args.daytona_cap_mb, not args.no_instabox, not args.no_daytona)
    assign_shards(jobs, slots)
    active_slots = [s for s in slots if s.jobs]

    print_plan(slots, len(jobs), skipped)
    if args.plan or not jobs:
        return 0

    STATE_LOG.parent.mkdir(parents=True, exist_ok=True)
    vms: list[CloudVM] = []
    pulled_per_vm: dict[str, set[str]] = {s.name: set() for s in active_slots}
    failed_jobs: list[str] = []

    try:
        with tempfile.TemporaryDirectory() as td:
            payload_tar = build_payload_tarball(pathlib.Path(td) / "champsim_payload.tar.gz")
            log(f"Built payload tarball: {payload_tar.stat().st_size / 1024:.1f} KB")
            with ThreadPoolExecutor(max_workers=len(active_slots)) as pool:
                futs = {pool.submit(provision_and_start_node, s, payload_tar): s for s in active_slots}
                for fut in as_completed(futs):
                    s = futs[fut]
                    vm = fut.result()
                    vms.append(vm)

        done_vms: set[str] = set()
        t_start = time.time()
        while len(done_vms) < len(vms):
            time.sleep(args.poll_sec)
            snapshot_state: dict[str, dict] = {}
            for vm in vms:
                nm = vm.slot.name
                if nm in done_vms:
                    snapshot_state[nm] = {"state": "DONE", "pulled": len(pulled_per_vm[nm]), "total": len(vm.slot.jobs)}
                    continue
                try:
                    st_out = vm.exec_bash(
                        f"""WORK={shlex.quote(vm.work_dir)}
cat "$WORK/STATUS" 2>/dev/null || echo UNKNOWN
grep -c '^OK|' "$WORK/progress.log" 2>/dev/null || true
grep -c '^FAIL|' "$WORK/progress.log" 2>/dev/null || true
ps -eo comm | grep -c '^champsim_' || true
""",
                        timeout=120,
                    )
                    lines = [ln.strip() for ln in st_out.splitlines() if ln.strip()]
                    status_str = lines[0] if lines else "UNKNOWN"
                    ok_cnt = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 0
                    fail_cnt = int(lines[2]) if len(lines) > 2 and lines[2].isdigit() else 0
                    procs = int(lines[3]) if len(lines) > 3 and lines[3].isdigit() else 0

                    newly_ok, bad = pull_new_jsons(vm, vm.slot.jobs, pulled_per_vm[nm])
                    if bad:
                        failed_jobs.extend(f"{nm}:{b}" for b in bad)
                    if newly_ok:
                        log(f"[{nm}] pulled +{newly_ok} verified JSONs ({len(pulled_per_vm[nm])}/{len(vm.slot.jobs)})")

                    if status_str == "ALL_DONE" and procs == 0:
                        newly2, bad2 = pull_new_jsons(vm, vm.slot.jobs, pulled_per_vm[nm])
                        if bad2:
                            failed_jobs.extend(f"{nm}:{b}" for b in bad2)
                        prog_txt = vm.exec_bash(f"cat {shlex.quote(vm.work_dir + '/progress.log')} 2>/dev/null || true", timeout=60)
                        for pl in prog_txt.splitlines():
                            if pl.startswith("FAIL|"):
                                failed_jobs.append(f"{nm}:{pl}")
                        (ROOT / "results" / "logs" / f"{nm}_progress.log").write_text(prog_txt, encoding="utf-8")
                        done_vms.add(nm)
                        log(f"[{nm}] ALL_DONE! ok={ok_cnt} fail={fail_cnt} verified={len(pulled_per_vm[nm])}/{len(vm.slot.jobs)}")

                    snapshot_state[nm] = {
                        "state": status_str,
                        "ok": ok_cnt,
                        "fail": fail_cnt,
                        "procs": procs,
                        "pulled": len(pulled_per_vm[nm]),
                        "total": len(vm.slot.jobs),
                    }
                except Exception as e:
                    log(f"[{nm}] poll error (will retry next cycle): {e}")
                    snapshot_state[nm] = {"state": "POLL_ERR", "error": str(e), "pulled": len(pulled_per_vm[nm]), "total": len(vm.slot.jobs)}

            total_pulled = sum(len(v) for v in pulled_per_vm.values())
            STATE_LOG.write_text(
                json.dumps(
                    {
                        "elapsed_sec": round(time.time() - t_start, 1),
                        "total_pulled": total_pulled,
                        "total_jobs": len(jobs),
                        "failed_jobs": failed_jobs,
                        "nodes": snapshot_state,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            log(f"[PROGRESS] {total_pulled}/{len(jobs)} verified JSONs pulled | done VMs: {len(done_vms)}/{len(vms)} | elapsed={(time.time()-t_start)/60:.1f}m")

        still_missing, _ = build_all_jobs(only_groups)
        log(f"[COMPLETE] elapsed={(time.time()-t_start)/60:.1f}m remaining_missing={len(still_missing)} failed={len(failed_jobs)}")
        if failed_jobs:
            log("Failed list:\n  " + "\n  ".join(failed_jobs))
        return 1 if (still_missing or failed_jobs) else 0
    finally:
        if not args.keep_vms:
            cleanup_all(vms)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run full dual-prefetcher + LOO cloud matrix across Instabox & Daytona")
    ap.add_argument("--plan", action="store_true", help="Print sharding plan and exit")
    ap.add_argument("--yes", action="store_true", help="Execute cloud runs")
    ap.add_argument("--groups", nargs="*", choices=["g_new_nopref", "loo_pref", "loo_spp"], help="Optional group filter")
    ap.add_argument("--daytona-snapshot", default="daytona-large")
    ap.add_argument("--daytona-cap-mb", type=float, default=1550.0)
    ap.add_argument("--poll-sec", type=int, default=45)
    ap.add_argument("--no-instabox", action="store_true")
    ap.add_argument("--no-daytona", action="store_true")
    ap.add_argument("--keep-vms", action="store_true", help="Do not delete sandboxes after exit")
    args = ap.parse_args()
    if not args.plan and not args.yes:
        args.plan = True
    return run_fleet(args)


if __name__ == "__main__":
    raise SystemExit(main())
