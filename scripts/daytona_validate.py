#!/usr/bin/env python3
"""Validate the top search configs on all 8 traces (50M+150M) on Daytona."""
import base64
import io
import pathlib
import tarfile
import time

from daytona import Daytona, DaytonaConfig

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = ROOT / "env" / "daytona.env"
OUT = ROOT / "results" / "raw" / "mdpp_validate"
ASSIGN = {
    1: ("mpppb-mdpp-1", ["429.mcf-22B", "483.xalancbmk-127B", "450.soplex-92B"]),
    2: ("mpppb-mdpp-2", ["400.perlbench-41B", "403.gcc-16B", "470.lbm-1274B"]),
    3: ("mpppb-mdpp-3", ["437.leslie3d-134B", "410.bwaves-945B"]),
}
CONFIGS = {
    "c4_highbypass": "MPPPB_DT1=30 MPPPB_DT2=150",
    "c14_theta_high": "MPPPB_THETA=130 MPPPB_THETA2=160",
}


def shell_for(traces):
    lines = ["#!/usr/bin/env bash", "set -u", 'cd "$HOME/ChampSim"', "mkdir -p val", ""]
    lines.append("run() {")
    lines.append('  local name="$1" envs="$2" tr="$3"')
    lines.append('  MPPPB_PROFILE=author1 MPPPB_STATS=1 env $envs ./bin/champsim_mpppb_mdpp '
                 '-w 50000000 -i 150000000 --hide-heartbeat --json "val/${name}_${tr}.json" '
                 '"traces/${tr}.champsimtrace.xz" > "val/${name}_${tr}.log" 2>&1')
    lines.append("}")
    lines.append("")
    pairs = [(name, envs, tr) for name, envs in CONFIGS.items() for tr in traces]
    for i in range(0, len(pairs), 4):
        for name, envs, tr in pairs[i:i + 4]:
            lines.append(f'run {name} "{envs}" {tr} &')
        lines.append("wait")
        lines.append("")
    lines.append("echo VAL_DONE")
    return "\n".join(lines)


def main():
    pairs = dict(l.strip().split("=", 1) for l in ENV.read_text().splitlines() if l.strip())
    clients = {i: Daytona(DaytonaConfig(api_key=pairs[f"DAYTONA_API_KEY_{i}"], api_url="https://app.daytona.io/api", target="us")) for i in (1, 2, 3)}
    sandboxes = {}
    for idx, (name, traces) in ASSIGN.items():
        sb = clients[idx].get(name)
        script = shell_for(traces)
        tmp = ROOT / "results" / "raw" / f"validate_{idx}.sh"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(script.encode("utf-8"))
        sb.fs.upload_file(str(tmp), "validate.sh")
        print(idx, "launch", sb.process.exec("cd $HOME && nohup bash $HOME/validate.sh > $HOME/validate.log 2>&1 & echo LAUNCHED", timeout=60).result.strip(), flush=True)
        sandboxes[idx] = sb

    expect = sum(len(t) for _, t in ASSIGN.values()) * len(CONFIGS)
    deadline = time.time() + 120 * 60
    while time.time() < deadline:
        time.sleep(120)
        done = 0
        busy = 0
        for idx, sb in sandboxes.items():
            st = sb.process.exec("cd $HOME/ChampSim && echo jsons=$(find val -name '*.json' | wc -l) procs=$(ps -eo comm | grep -c '^champsim' || true)", timeout=60).result
            try:
                done += int(st.split("jsons=")[1].split()[0])
                busy += int(st.split("procs=")[1].split()[0])
            except Exception:
                pass
        print("progress", done, "json", busy, "procs", flush=True)
        if done >= expect or (busy == 0 and done > 0):
            break

    OUT.mkdir(parents=True, exist_ok=True)
    for idx, sb in sandboxes.items():
        resp = sb.process.exec("cd $HOME/ChampSim && tar czf - val | base64 -w0", timeout=300)
        raw = base64.b64decode(resp.result.strip())
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
            tf.extractall(OUT / f"box{idx}")
        print("downloaded", idx, flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()