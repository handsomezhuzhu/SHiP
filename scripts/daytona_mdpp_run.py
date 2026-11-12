#!/usr/bin/env python3
"""Run the single-core MDPP matrix on three Daytona sandboxes.

Reads keys from env/daytona.env (not committed). Uploads the module/config,
runs setup, launches 8 traces in the background, polls, and downloads results.
"""
import base64
import io
import os
import pathlib
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor

from daytona import Daytona, DaytonaConfig

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = ROOT / "env" / "daytona.env"
API = "https://app.daytona.io/api"
TARGET = "us"

ASSIGN = {
    1: ("mpppb-mdpp-1", ["429.mcf-22B", "483.xalancbmk-127B", "450.soplex-92B"]),
    2: ("mpppb-mdpp-2", ["400.perlbench-41B", "403.gcc-16B", "470.lbm-1274B"]),
    3: ("mpppb-mdpp-3", ["437.leslie3d-134B", "410.bwaves-945B"]),
}
ALL_TRACES = [t for _, ts in ASSIGN.values() for t in ts]
OUT = ROOT / "results" / "raw" / "mdpp_daytona"


def keys():
    pairs = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line and "=" in line:
            k, v = line.split("=", 1)
            pairs[k.strip()] = v.strip()
    return pairs


def client_for(pairs, idx):
    return Daytona(DaytonaConfig(api_key=pairs[f"DAYTONA_API_KEY_{idx}"], api_url=API, target=TARGET))


def upload_common(sb):
    for folder in ("champsim_modules", "champsim_modules/mpppb", "configs"):
        try:
            sb.fs.create_folder(folder)
        except Exception:
            pass
    sb.fs.upload_file(str(ROOT / "champsim_modules/mpppb/mpppb.cc"), "champsim_modules/mpppb/mpppb.cc")
    sb.fs.upload_file(str(ROOT / "champsim_modules/mpppb/mpppb.h"), "champsim_modules/mpppb/mpppb.h")
    sb.fs.upload_file(str(ROOT / "configs/champsim_mpppb_mdpp.json"), "configs/champsim_mpppb_mdpp.json")
    sb.fs.upload_file(str(ROOT / "env/ChampSim/src/cache.cc"), "cache.cc")
    sb.fs.upload_file(str(ROOT / "scripts/daytona_setup.sh"), "setup.sh")
    sb.fs.upload_file(str(ROOT / "scripts/daytona_run_mdpp.sh"), "run.sh")


def setup_one(pairs, idx):
    name, traces = ASSIGN[idx]
    client = client_for(pairs, idx)
    sb = client.get(name)
    print(f"[{idx}] {name} upload", flush=True)
    upload_common(sb)
    print(f"[{idx}] setup start", flush=True)
    resp = sb.process.exec("bash $HOME/setup.sh", timeout=1800)
    print(f"[{idx}] setup rc={getattr(resp, 'exit_code', '?')}", flush=True)
    print(getattr(resp, "result", "")[-1200:], flush=True)
    for tr in traces:
        print(f"[{idx}] upload {tr}", flush=True)
        sb.fs.upload_file(str(ROOT / "traces" / f"{tr}.champsimtrace.xz"),
                          f"ChampSim/traces/{tr}.champsimtrace.xz", timeout=1800)
    return idx, sb


def launch(pairs, idx, sb):
    name, traces = ASSIGN[idx]
    cmd = "cd $HOME && nohup bash $HOME/run.sh " + " ".join(traces) + " > $HOME/run.log 2>&1 & echo LAUNCHED"
    resp = sb.process.exec(cmd, timeout=60)
    print(f"[{idx}] launch", getattr(resp, "result", "").strip(), flush=True)


def progress(sb):
    cmd = "cd $HOME/ChampSim && echo jsons=$(ls results/*.json 2>/dev/null | wc -l) procs=$(pgrep -c champsim 2>/dev/null || echo 0)"
    return sb.process.exec(cmd, timeout=60).result.strip()


def download(idx, sb):
    resp = sb.process.exec("cd $HOME/ChampSim && tar czf - results | base64 -w0", timeout=300)
    data = getattr(resp, "result", "").strip()
    raw = base64.b64decode(data)
    OUT.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        tf.extractall(OUT / f"box{idx}")
    print(f"[{idx}] downloaded", flush=True)


def main():
    pairs = keys()
    sandboxes = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(setup_one, pairs, i) for i in (1, 2, 3)]
        for fut in futures:
            idx, sb = fut.result()
            sandboxes[idx] = sb
    for idx, sb in sandboxes.items():
        launch(pairs, idx, sb)

    deadline = time.time() + 90 * 60
    while time.time() < deadline:
        time.sleep(120)
        status = {i: progress(sb) for i, sb in sandboxes.items()}
        print("progress", status, flush=True)
        done = sum(int(s.split("jsons=")[1].split()[0]) for s in status.values())
        busy = sum(int(s.split("procs=")[1].split()[0]) for s in status.values())
        if done >= len(ALL_TRACES) or (done >= len(ALL_TRACES) - 1 and busy == 0):
            break
        if busy == 0 and done < len(ALL_TRACES):
            print("all processes exited but results incomplete; stopping poll", flush=True)
            break

    for idx, sb in sandboxes.items():
        download(idx, sb)
    print("DONE", flush=True)


if __name__ == "__main__":
    sys.exit(main())