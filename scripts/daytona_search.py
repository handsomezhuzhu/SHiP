#!/usr/bin/env python3
"""Run a one-factor-at-a-time tau/pi search on mcf+xalan (5M+5M) on Daytona."""
import base64
import io
import pathlib
import tarfile
import time

from daytona import Daytona, DaytonaConfig

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = ROOT / "env" / "daytona.env"
OUT = ROOT / "results" / "raw" / "mdpp_search"
TRACES = ("429.mcf-22B", "483.xalancbmk-127B")

CONFIGS = [
    ("c0_author1", ""),
    ("c1_nobypass", "MPPPB_DT1=1000 MPPPB_DT2=1000"),
    ("c2_lowbypass", "MPPPB_DT1=100 MPPPB_DT2=400"),
    ("c3_midbypass", "MPPPB_DT1=80 MPPPB_DT2=320"),
    ("c4_highbypass", "MPPPB_DT1=30 MPPPB_DT2=150"),
    ("c5_prom60", "MPPPB_PROMOTE=60"),
    ("c6_prom100", "MPPPB_PROMOTE=100"),
    ("c7_prom120", "MPPPB_PROMOTE=120"),
    ("c8_plv_low", "MPPPB_PLV0T=0 MPPPB_PLV0P=0 MPPPB_PLV1T=20 MPPPB_PLV1P=12 MPPPB_PLV2T=35 MPPPB_PLV2P=15"),
    ("c9_plv_mid", "MPPPB_PLV0T=30 MPPPB_PLV0P=0 MPPPB_PLV1T=40 MPPPB_PLV1P=12 MPPPB_PLV2T=48 MPPPB_PLV2P=15"),
    ("c10_plv_high", "MPPPB_PLV0T=50 MPPPB_PLV0P=0 MPPPB_PLV1T=60 MPPPB_PLV1P=12 MPPPB_PLV2T=70 MPPPB_PLV2P=15"),
    ("c11_train96", "MPPPB_TRAIN_THRESHOLD=96"),
    ("c12_train160", "MPPPB_TRAIN_THRESHOLD=160"),
    ("c13_theta_low", "MPPPB_THETA=90 MPPPB_THETA2=120"),
    ("c14_theta_high", "MPPPB_THETA=130 MPPPB_THETA2=160"),
    ("c15_lowbypass_p60", "MPPPB_DT1=100 MPPPB_DT2=400 MPPPB_PROMOTE=60"),
    ("c16_plvmid_train96", "MPPPB_PLV0T=30 MPPPB_PLV0P=0 MPPPB_PLV1T=40 MPPPB_PLV1P=12 MPPPB_PLV2T=48 MPPPB_PLV2P=15 MPPPB_TRAIN_THRESHOLD=96"),
    ("c17_nobypass_p60", "MPPPB_DT1=1000 MPPPB_DT2=1000 MPPPB_PROMOTE=60"),
]


def shell_script():
    lines = ["#!/usr/bin/env bash", "set -u", 'cd "$HOME/ChampSim"', "mkdir -p search", ""]
    lines.append("run() {")
    lines.append('  local name="$1" envs="$2" tr="$3"')
    lines.append('  MPPPB_PROFILE=author1 MPPPB_STATS=1 env $envs ./bin/champsim_mpppb_mdpp '
                 '-w 5000000 -i 5000000 --hide-heartbeat --json "search/${name}_${tr}.json" '
                 '"traces/${tr}.champsimtrace.xz" > "search/${name}_${tr}.log" 2>&1')
    lines.append("}")
    lines.append("")
    for i in range(0, len(CONFIGS), 2):
        for name, envs in CONFIGS[i:i + 2]:
            for tr in TRACES:
                lines.append(f'run {name} "{envs}" {tr} &')
        lines.append("wait")
        lines.append("")
    lines.append("echo SEARCH_DONE")
    return "\n".join(lines)


def main():
    pairs = dict(l.strip().split("=", 1) for l in ENV.read_text().splitlines() if l.strip())
    client = Daytona(DaytonaConfig(api_key=pairs["DAYTONA_API_KEY_1"], api_url="https://app.daytona.io/api", target="us"))
    sb = client.get("mpppb-mdpp-1")
    script = shell_script()
    tmp = ROOT / "results" / "raw" / "mdpp_search.sh"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(script)
    sb.fs.upload_file(str(tmp), "search.sh")
    print("launch", sb.process.exec("cd $HOME && nohup bash $HOME/search.sh > $HOME/search.log 2>&1 & echo LAUNCHED", timeout=60).result.strip(), flush=True)

    deadline = time.time() + 60 * 60
    while time.time() < deadline:
        time.sleep(90)
        st = sb.process.exec("cd $HOME/ChampSim && echo jsons=$(find search -name '*.json' | wc -l) procs=$(ps -eo comm | grep -c '^champsim' || true); tail -1 $HOME/search.log", timeout=60).result.strip()
        print(st, flush=True)
        if "jsons=" in st and int(st.split("jsons=")[1].split()[0]) >= len(CONFIGS) * 2:
            break
        if "SEARCH_DONE" in st:
            break

    resp = sb.process.exec("cd $HOME/ChampSim && tar czf - search | base64 -w0", timeout=300)
    raw = base64.b64decode(resp.result.strip())
    OUT.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        tf.extractall(OUT)
    print("downloaded", OUT, flush=True)


if __name__ == "__main__":
    main()