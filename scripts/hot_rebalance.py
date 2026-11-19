#!/usr/bin/env python3
"""Hot-rebalance remaining unstarted jobs from throttled Instabox VMs onto idle fast Daytona VMs.

Keeps all 8 live cloud VMs (5 Instabox + 3 Daytona) and their compiled ChampSim binaries intact:
  1. Verifies SIGTERM on parent worker leaves in-flight subshells alive on Daytona test.
  2. Detaches the old coordinator process without firing VM deletion cleanup.
  3. Freezes full-ib1..ib5 at ONLY their currently executing 4 jobs each (zero wasted sunk CPU).
  4. Moves all unstarted queued jobs onto full-dt1..dt3 (12 unthrottled fast cores, 9 GB free each).
  5. Monitors all 8 VMs, pulls & verifies all JSONs incrementally, steals stragglers if needed,
     and cleans up all 8 sandboxes once 100% of remaining jobs verify locally.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import pathlib
import shlex
import subprocess
import sys
import tempfile
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from daytona import Daytona, DaytonaConfig  # noqa: E402
from run_3groups_cloud import DAYTONA_API, DAYTONA_TARGET, INSTABOX_EXE  # noqa: E402
import run_full_cloud as rfc  # noqa: E402

STATUS_FILE = ROOT / "results" / "logs" / "hot_rebalance_status.json"


def log(msg: str) -> None:
    rfc.log(msg)


def connect_existing_vms() -> tuple[list[rfc.InstaboxVM], list[rfc.DaytonaVM]]:
    ib_vms: list[rfc.InstaboxVM] = []
    for i in range(1, 6):
        slot = rfc.NodeSlot(name=f"full-ib{i}", provider="instabox", max_jobs=4, cap_mb=12000.0)
        vm = rfc.InstaboxVM(slot)
        vm.keep_awake()
        tok = json.loads(vm._ib("ssh-token", slot.name, "--json").stdout.decode("utf-8"))
        vm.ssh_host = tok["host"]
        vm.ssh_port = int(tok.get("port", 2222))
        vm.ssh_token = tok["token"]
        ib_vms.append(vm)

    dt_vms: list[rfc.DaytonaVM] = []
    for idx, key in enumerate(rfc.load_daytona_keys(), start=1):
        slot = rfc.NodeSlot(name=f"full-dt{idx}", provider="daytona", max_jobs=4, cap_mb=6000.0, api_key=key)
        vm = rfc.DaytonaVM(slot)
        items = list(getattr(vm.client.list(), "items", vm.client.list()))
        if not items:
            raise RuntimeError(f"Expected live Daytona sandbox on key #{idx}, found 0")
        vm.sb = items[0]
        dt_vms.append(vm)
    return ib_vms, dt_vms


def test_kill_parent_preserves_subshell(dt1: rfc.DaytonaVM) -> None:
    script = r"""
rm -f /tmp/subshell_ok
cat > /tmp/wtest.sh <<'EOS'
#!/usr/bin/env bash
run_one() {
  sleep 4
  echo OK > /tmp/subshell_ok
}
run_one &
while true; do sleep 1; done
EOS
nohup bash /tmp/wtest.sh </dev/null >/tmp/wtest.log 2>&1 &
WPID=$!
sleep 1
kill -TERM "$WPID"
sleep 5
cat /tmp/subshell_ok 2>/dev/null || echo MISSING
rm -f /tmp/wtest.sh /tmp/wtest.log /tmp/subshell_ok
"""
    out = dt1.exec_bash(script, timeout=45).strip()
    if out != "OK":
        raise RuntimeError(f"Parent-kill safety test failed on dt1: {out!r}")
    log("[safety] verified parent SIGTERM leaves child subshells intact (OK)")


def detach_old_coordinator() -> None:
    ps_cmd = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_full_cloud.py*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('KILLED_PID=' + $_.ProcessId) }"
    )
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    log(f"[detach] {res.stdout.strip() or 'no running run_full_cloud.py pid found'}")
    if res.returncode != 0 and res.stderr.strip():
        log(f"[detach stderr] {res.stderr.strip()}")


def freeze_ib_at_inflight(vm: rfc.InstaboxVM, all_jobs_by_rel: dict[str, rfc.JobSpec]) -> set[str]:
    """Stop parent worker.sh loop (leaving in-flight children running), return in-flight rel paths."""
    out = vm.exec_bash(
        r"""WORK=/data/home/full_run
# Find parent worker.sh (PPID=1 or oldest worker.sh) and halt further scheduling without killing champsim children
PIDS=$(ps -eo pid,ppid,args | awk '$2==1 && /\/data\/home\/full_run\/worker\.sh/ {print $1}')
: > "$WORK/tasks.tsv"
if [ -n "$PIDS" ]; then
  kill -TERM $PIDS 2>/dev/null || true
fi
sleep 1
echo "=== INFLIGHT ==="
ps -eo args | grep '/data/home/full_run/ChampSim/bin/champsim_' | grep -v grep || true
""",
        timeout=60,
    )
    inflight_rels: set[str] = set()
    for ln in out.splitlines():
        ln = ln.strip()
        marker = "/data/home/full_run/out/"
        if marker in ln and ".json.tmp" in ln:
            part = ln.split(marker, 1)[1].split(".json.tmp", 1)[0] + ".json"
            if part in all_jobs_by_rel:
                inflight_rels.add(part)
    log(f"[{vm.slot.name}] frozen parent loop; active in-flight jobs ({len(inflight_rels)}): {sorted(inflight_rels)}")
    return inflight_rels


def measured_dt_seconds() -> dict[str, float]:
    """Compute empirical Daytona seconds per trace from finished progress logs."""
    by_tr: dict[str, list[int]] = {}
    for i in (1, 2, 3):
        p = ROOT / "results" / "logs" / f"full-dt{i}_progress.log"
        if not p.exists():
            continue
        for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ln.startswith("OK|"):
                _, jid, sec, _ = ln.split("|")
                _, _, tr = jid.split("__")
                by_tr.setdefault(tr, []).append(int(sec))
    return {k: sum(v) / len(v) for k, v in by_tr.items() if v}


def assign_jobs_to_daytona(unstarted: list[rfc.JobSpec], dt_vms: list[rfc.DaytonaVM]) -> None:
    dt_meas = measured_dt_seconds()
    # Empirical multiplier for faster suites (cvp1/qc/6xx compute) vs est_sec
    def est_dt_sec(j: rfc.JobSpec) -> float:
        tr_name = j.trace.name
        if tr_name in dt_meas:
            return dt_meas[tr_name]
        if tr_name.startswith(("cvp1_", "qc_srv")):
            return j.est_sec * 0.60
        if j.group == "g_new_nopref":
            return j.est_sec * 0.85
        return float(j.est_sec)

    by_trace: dict[str, list[rfc.JobSpec]] = {}
    for j in unstarted:
        by_trace.setdefault(j.trace.name, []).append(j)

    bundles = sorted(by_trace.values(), key=lambda js: sum(est_dt_sec(x) for x in js), reverse=True)
    for s_vm in dt_vms:
        s_vm.slot.jobs = []
        s_vm.slot.traces_mb = 0.0
        s_vm.slot.est_cpu_sec = 0.0
        s_vm.slot.trace_names = set()

    for b in bundles:
        tr = b[0].trace
        b_sec = sum(est_dt_sec(x) for x in b)
        cands = [vm for vm in dt_vms if vm.slot.traces_mb + tr.mb <= vm.slot.cap_mb]
        if not cands:
            cands = dt_vms
        best = min(cands, key=lambda vm: (vm.slot.est_wall_sec, vm.slot.traces_mb))
        if tr.name not in best.slot.trace_names:
            best.slot.trace_names.add(tr.name)
            best.slot.traces_mb += tr.mb
        best.slot.jobs.extend(b)
        best.slot.est_cpu_sec += b_sec

    # If one trace is heavily dominating or bundles < slots, balance cleanly; else keep per-node LPT sort
    for vm in dt_vms:
        vm.slot.jobs.sort(key=lambda j: -est_dt_sec(j))


def launch_daytona_shard(vm: rfc.DaytonaVM) -> None:
    slot = vm.slot
    log(f"[{slot.name}] wiping old traces & staging {len(slot.trace_names)} new traces ({slot.traces_mb:.1f} MB) for {len(slot.jobs)} jobs...")
    vm.exec_bash(
        f"""set -euo pipefail
WORK={shlex.quote(vm.work_dir)}
rm -rf "$WORK/traces" "$WORK/out" "$WORK/err" "$WORK/STATUS" "$WORK/progress.log" "$WORK/worker.log"
mkdir -p "$WORK/traces" "$WORK/out" "$WORK/err"
df -h "$WORK"
""",
        timeout=120,
    )
    uploaded: set[str] = set()
    for j in slot.jobs:
        if j.trace.name in uploaded:
            continue
        local_tr = ROOT / j.trace_subdir / f"{j.trace.name}.champsimtrace.xz"
        vm.upload_file(local_tr, f"{vm.work_dir}/traces/{j.trace.name}.champsimtrace.xz")
        uploaded.add(j.trace.name)

    with tempfile.TemporaryDirectory() as td:
        tp = pathlib.Path(td) / "tasks.tsv"
        wp = pathlib.Path(td) / "worker.sh"
        tp.write_text(rfc.serialize_tasks_tsv(slot.jobs), encoding="utf-8", newline="\n")
        wp.write_text(rfc.make_worker_script(vm.work_dir, slot.max_jobs), encoding="utf-8", newline="\n")
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
    log(f"[{slot.name}] launched FAST Daytona worker ({len(slot.jobs)} jobs, est {slot.est_wall_sec/60:.1f}m)")


def main() -> int:
    ib_vms, dt_vms = connect_existing_vms()
    all_vms: list[rfc.CloudVM] = [*ib_vms, *dt_vms]
    try:
        test_kill_parent_preserves_subshell(dt_vms[0])
        detach_old_coordinator()

        all_remaining_init, _ = rfc.build_all_jobs()
        by_rel = {j.rel_out: j for j in all_remaining_init}

        # Pull any just-finished JSONs on ib1..ib5 and freeze their queues
        ib_inflight_rels: dict[str, set[str]] = {}
        pulled_ib: dict[str, set[str]] = {vm.slot.name: set() for vm in ib_vms}
        for vm in ib_vms:
            inflight = freeze_ib_at_inflight(vm, by_rel)
            ib_inflight_rels[vm.slot.name] = inflight
            # Populate vm.slot.jobs with ONLY currently missing jobs matching traces already on this ib VM
            # Wait: pull everything ready on this ib VM right now!
            vm.slot.jobs = list(all_remaining_init)
            n_ok, bad = rfc.pull_new_jsons(vm, vm.slot.jobs, pulled_ib[vm.slot.name])
            if n_ok:
                log(f"[{vm.slot.name}] pulled +{n_ok} newly completed JSONs before rebalance")
            # Restrict ib vm.slot.jobs to ONLY its in-flight jobs
            vm.slot.jobs = [by_rel[r] for r in sorted(inflight) if r in by_rel]

        # Recompute still-pending on local disk AFTER pulling ib1..ib5
        still_pending, _ = rfc.build_all_jobs()
        all_inflight = set().union(*ib_inflight_rels.values())
        unstarted = [j for j in still_pending if j.rel_out not in all_inflight]

        log(
            f"[rebalance summary] total_pending={len(still_pending)} | "
            f"ib_inflight={len(all_inflight)} (stay on 5 Instabox) | "
            f"unstarted={len(unstarted)} (move to 3 fast Daytona)"
        )

        assign_jobs_to_daytona(unstarted, dt_vms)
        for vm in dt_vms:
            s = vm.slot
            log(
                f"  {s.name:9s} jobs={len(s.jobs):3d} traces={len(s.trace_names):2d} "
                f"mb={s.traces_mb:6.1f} est_wall={s.est_wall_sec/60:5.1f}m | {sorted(s.trace_names)}"
            )

        with ThreadPoolExecutor(max_workers=len(dt_vms)) as pool:
            futs = [pool.submit(launch_daytona_shard, vm) for vm in dt_vms if vm.slot.jobs]
            for f in as_completed(futs):
                f.result()

        pulled_per_vm: dict[str, set[str]] = {vm.slot.name: set() for vm in all_vms}
        done_vms: set[str] = set()
        for vm in dt_vms:
            if not vm.slot.jobs:
                done_vms.add(vm.slot.name)
        for vm in ib_vms:
            if not vm.slot.jobs:
                done_vms.add(vm.slot.name)

        t0 = time.time()
        stole_round = 0
        while True:
            rem_chk_top, _ = rfc.build_all_jobs()
            if not rem_chk_top:
                log("[DONE] 0 missing jobs remaining!")
                break
            time.sleep(45)
            snap: dict[str, dict] = {}
            for vm in all_vms:
                nm = vm.slot.name
                if nm in done_vms:
                    snap[nm] = {"state": "DONE", "pulled": len(pulled_per_vm[nm]), "total": len(vm.slot.jobs)}
                    continue
                try:
                    st_out = vm.exec_bash(
                        f"""WORK={shlex.quote(vm.work_dir)}
cat "$WORK/STATUS" 2>/dev/null || echo RUNNING
ps -eo comm | grep -c '^champsim_' || true
""",
                        timeout=120,
                    )
                    lines = [ln.strip() for ln in st_out.splitlines() if ln.strip()]
                    st_str = lines[0] if lines else "RUNNING"
                    procs = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 0

                    newly_ok, bad = rfc.pull_new_jsons(vm, vm.slot.jobs, pulled_per_vm[nm])
                    if newly_ok:
                        log(f"[{nm}] pulled +{newly_ok} verified JSONs ({len(pulled_per_vm[nm])}/{len(vm.slot.jobs)})")
                    if bad:
                        log(f"[{nm}] BAD JSONs: {bad}")

                    finished = (procs == 0) if vm.slot.provider == "instabox" else (st_str == "ALL_DONE" and procs == 0)
                    if finished:
                        rfc.pull_new_jsons(vm, vm.slot.jobs, pulled_per_vm[nm])
                        done_vms.add(nm)
                        log(f"[{nm}] FINISHED shard ({len(pulled_per_vm[nm])}/{len(vm.slot.jobs)}, procs=0)")

                    snap[nm] = {
                        "state": "DONE" if nm in done_vms else st_str,
                        "procs": procs,
                        "pulled": len(pulled_per_vm[nm]),
                        "total": len(vm.slot.jobs),
                    }
                except Exception as e:
                    log(f"[{nm}] poll warning (will retry): {e}")
                    snap[nm] = {"state": "POLL_ERR", "error": str(e), "pulled": len(pulled_per_vm[nm]), "total": len(vm.slot.jobs)}

            rem_now, _ = rfc.build_all_jobs()
            done_total = 354 - len(rem_now)
            STATUS_FILE.write_text(
                json.dumps(
                    {
                        "elapsed_min": round((time.time() - t0) / 60.0, 1),
                        "completed_new_jobs": done_total,
                        "total_new_jobs": 354,
                        "remaining": len(rem_now),
                        "nodes": snap,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            log(f"[REBAL PROGRESS] {done_total}/354 verified | remaining={len(rem_now)} | done_vms={len(done_vms)}/{len(all_vms)} | elapsed={(time.time()-t0)/60:.1f}m")

            if not rem_now:
                break

            # Speculative tail steal: if all 3 fast Daytona VMs finished while slow Instabox still crawls
            if all(vm.slot.name in done_vms for vm in dt_vms) and rem_now and stole_round < 2:
                stole_round += 1
                log(f"[steal #{stole_round}] Daytona fleet idle while {len(rem_now)} jobs still pending on Instabox; racing on Daytona...")
                assign_jobs_to_daytona(rem_now, dt_vms)
                with ThreadPoolExecutor(max_workers=len(dt_vms)) as pool:
                    futs = []
                    for vm in dt_vms:
                        if vm.slot.jobs:
                            done_vms.discard(vm.slot.name)
                            pulled_per_vm[vm.slot.name] = set()
                            futs.append(pool.submit(launch_daytona_shard, vm))
                    for f in as_completed(futs):
                        f.result()

        rem_final, _ = rfc.build_all_jobs()
        log(f"[ALL COMPLETE] remaining_missing={len(rem_final)}")
        return 0 if not rem_final else 1
    finally:
        # Clean up ALL 8 sandboxes ONLY when all remaining jobs are verified OR let cleanup_all sweep everything cleanly
        rem_chk, _ = rfc.build_all_jobs()
        if not rem_chk:
            log("[cleanup] 0 remaining missing jobs -> deleting all 8 sandboxes...")
            rfc.cleanup_all(all_vms)
        else:
            log(f"[cleanup] skipping auto-delete because {len(rem_chk)} jobs still missing (preserve binaries/traces for resume)")


if __name__ == "__main__":
    raise SystemExit(main())
