#!/usr/bin/env python3
"""Fetch and verify the generalized external benchmark suite into traces_new/.

Sources:
  1. DPC-3 SPEC CPU2017 Speed (10 representative 6xx traces, direct .xz)
  2. Zenodo 20043527: GAP Graph Analytics + XSBench HPC (HTTP-Range ZIP64 extract)
  3. Zenodo 10199624: Improved Converted CVP-1 Traces (HTTP-Range TAR extract)
  4. Zenodo 14045186: Qualcomm Server ChampSim Traces (HTTP-Range TAR extract)

Keeps existing traces/ untouched. Writes atomic .part -> final .champsimtrace.xz
files with XZ magic validation.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "traces_new"
XZ_MAGIC = b"\xfd7zXZ\x00"
XZ_TAIL = b"YZ"
CURL_BIN = shutil.which("curl.exe") or shutil.which("curl") or "curl"
_DPC3_SEM = threading.Semaphore(2)

DPC3_BASE = "https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu"
ZENODO_20043527 = "https://zenodo.org/records/20043527/files"
ZENODO_10199624_TAR = "https://zenodo.org/records/10199624/files/Improved_converted_traces.tar?download=1"
ZENODO_14045186_TAR = "https://zenodo.org/records/14045186/files/qualcomm_srv.tar?download=1"


@dataclass(frozen=True)
class TraceSpec:
    local_name: str
    suite: str
    kind: str  # "direct", "zip", "tar"
    url: str
    member: str = ""


TRACES: list[TraceSpec] = [
    # --- 10 DPC-3 SPEC CPU2017 Speed (6xx) ---
    TraceSpec("600.perlbench_s-210B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/600.perlbench_s-210B.champsimtrace.xz"),
    TraceSpec("602.gcc_s-734B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/602.gcc_s-734B.champsimtrace.xz"),
    TraceSpec("605.mcf_s-1554B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/605.mcf_s-1554B.champsimtrace.xz"),
    TraceSpec("607.cactuBSSN_s-2421B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/607.cactuBSSN_s-2421B.champsimtrace.xz"),
    TraceSpec("619.lbm_s-2676B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/619.lbm_s-2676B.champsimtrace.xz"),
    TraceSpec("620.omnetpp_s-874B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/620.omnetpp_s-874B.champsimtrace.xz"),
    TraceSpec("623.xalancbmk_s-10B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/623.xalancbmk_s-10B.champsimtrace.xz"),
    TraceSpec("649.fotonik3d_s-1176B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/649.fotonik3d_s-1176B.champsimtrace.xz"),
    TraceSpec("654.roms_s-1390B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/654.roms_s-1390B.champsimtrace.xz"),
    TraceSpec("657.xz_s-2302B.champsimtrace.xz", "dpc3_6xx", "direct", f"{DPC3_BASE}/657.xz_s-2302B.champsimtrace.xz"),
    # --- Zenodo 20043527: GAP + XSBench ---
    TraceSpec("bfs.twitter-10B.champsimtrace.xz", "zenodo_gap_xs", "zip", f"{ZENODO_20043527}/bfs_traces.zip?download=1", "bfs.twitter-10B.champsimtrace.xz"),
    TraceSpec("pr.web-16B.champsimtrace.xz", "zenodo_gap_xs", "zip", f"{ZENODO_20043527}/pr_traces.zip?download=1", "pr.web-16B.champsimtrace.xz"),
    TraceSpec("sssp.web-1185B.champsimtrace.xz", "zenodo_gap_xs", "zip", f"{ZENODO_20043527}/sssp_traces.zip?download=1", "sssp.web-1185B.champsimtrace.xz"),
    TraceSpec("xs.XL64unionized-66B.champsimtrace.xz", "zenodo_gap_xs", "zip", f"{ZENODO_20043527}/xs_XL64_traces.zip?download=1", "xs.XL64unionized-66B.champsimtrace.xz"),
    # --- Zenodo 10199624: Improved Converted CVP-1 ---
    TraceSpec("cvp1_srv_40.champsimtrace.xz", "zenodo_cvp1", "tar", ZENODO_10199624_TAR, "CVP1public/srv_40.champsimtrace.xz"),
    TraceSpec("cvp1_compute_int_38.champsimtrace.xz", "zenodo_cvp1", "tar", ZENODO_10199624_TAR, "CVP1public/compute_int_38.champsimtrace.xz"),
    TraceSpec("cvp1_compute_fp_8.champsimtrace.xz", "zenodo_cvp1", "tar", ZENODO_10199624_TAR, "CVP1public/compute_fp_8.champsimtrace.xz"),
    # --- Zenodo 14045186: Qualcomm Server ---
    TraceSpec("qc_srv0_ap.champsimtrace.xz", "zenodo_qualcomm", "tar", ZENODO_14045186_TAR, "srv0_ap.champsimtrace.xz"),
    TraceSpec("qc_srv106_ap.champsimtrace.xz", "zenodo_qualcomm", "tar", ZENODO_14045186_TAR, "srv106_ap.champsimtrace.xz"),
    TraceSpec("qc_srv115_ap.champsimtrace.xz", "zenodo_qualcomm", "tar", ZENODO_14045186_TAR, "srv115_ap.champsimtrace.xz"),
]


def _run_curl(args: list[str], retries: int = 3) -> bytes:
    last_err = ""
    for attempt in range(retries):
        p = subprocess.run([CURL_BIN, *args], capture_output=True)
        if p.returncode == 0:
            return p.stdout
        last_err = f"rc={p.returncode} stderr={p.stderr.decode('utf-8', 'ignore')[:200]}"
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"curl failed ({last_err})")


def curl_head_size(url: str) -> int:
    hdr = _run_curl(["-sIL", "--fail", "--max-time", "30", url])
    sizes = re.findall(rb"(?im)^content-length:\s*(\d+)\s*$", hdr)
    if not sizes:
        raise RuntimeError(f"No Content-Length for {url}")
    return int(sizes[-1])


def curl_range(url: str, start: int, end: int, timeout: int = 900) -> bytes:
    return _run_curl(["-sL", "--fail", "--max-time", str(timeout), "-r", f"{start}-{end}", url])


def curl_range_to_file(url: str, start: int, end: int, dest: pathlib.Path, timeout: int = 600) -> None:
    """Download [start, end] cleanly in 32 MiB resumable HTTP Range chunks."""
    total = end - start + 1
    chunk_sz = 32 * 1024 * 1024
    have = dest.stat().st_size if dest.exists() else 0
    if have > total:
        dest.unlink()
        have = 0
    while have < total:
        cur_start = start + have
        cur_end = min(end, cur_start + chunk_sz - 1)
        part = dest.with_suffix(dest.suffix + ".chk")
        ok = False
        last_err = ""
        for attempt in range(6):
            p = subprocess.run(
                [CURL_BIN, "-sL", "--fail", "--speed-time", "30", "--speed-limit", "1024",
                 "--max-time", str(timeout), "-r", f"{cur_start}-{cur_end}", "-o", str(part), url],
                capture_output=True,
            )
            want = cur_end - cur_start + 1
            if p.returncode == 0 and part.exists() and part.stat().st_size == want:
                with dest.open("ab") as fo, part.open("rb") as fi:
                    while buf := fi.read(4 * 1048576):
                        fo.write(buf)
                part.unlink(missing_ok=True)
                have += want
                ok = True
                break
            last_err = f"rc={p.returncode} {p.stderr.decode('utf-8', 'ignore')[:160]}"
            time.sleep(3 * (attempt + 1))
        if not ok:
            raise RuntimeError(f"range download failed for {url} [{cur_start}-{cur_end}]: {last_err}")


def verify_xz_file(path: pathlib.Path) -> bool:
    if not path.exists() or path.stat().st_size < 32:
        return False
    with path.open("rb") as f:
        head = f.read(6)
        f.seek(-2, 2)
        tail = f.read(2)
        return head == XZ_MAGIC and tail == XZ_TAIL


def fetch_direct(spec: TraceSpec, out_dir: pathlib.Path) -> pathlib.Path:
    with _DPC3_SEM:
        dst = out_dir / spec.local_name
        expected = curl_head_size(spec.url)
        if verify_xz_file(dst) and dst.stat().st_size == expected:
            print(f"[skip] {spec.local_name} ({expected / 1048576:.1f} MB)", flush=True)
            return dst
        part = out_dir / (spec.local_name + ".part")
        if part.exists() and part.stat().st_size > expected:
            part.unlink()
        last_err = ""
        for attempt in range(10):
            have = part.stat().st_size if part.exists() else 0
            if have == expected and verify_xz_file(part):
                part.replace(dst)
                print(f"[ok]   {spec.local_name} ({expected / 1048576:.1f} MB)", flush=True)
                return dst
            p = subprocess.run(
                [CURL_BIN, "-sL", "--fail", "-C", "-", "--speed-time", "30", "--speed-limit", "1024",
                 "--retry", "3", "--retry-delay", "3", "--max-time", "1200", "-o", str(part), spec.url],
                capture_output=True,
            )
            have = part.stat().st_size if part.exists() else 0
            if have == expected and verify_xz_file(part):
                part.replace(dst)
                print(f"[ok]   {spec.local_name} ({expected / 1048576:.1f} MB)", flush=True)
                return dst
            last_err = f"rc={p.returncode} have={have}/{expected} {p.stderr.decode('utf-8', 'ignore')[:160]}"
            print(f"[retry {attempt+1}] {spec.local_name}: {last_err}", flush=True)
            time.sleep(3 * min(attempt + 1, 5))
        raise RuntimeError(f"Failed direct download: {spec.url} ({last_err})")


def _parse_zip64_extras(extra: bytes, usize: int, csize: int, lfh_off: int) -> tuple[int, int, int]:
    ep = 0
    while ep + 4 <= len(extra):
        hid, hlen = struct.unpack_from("<HH", extra, ep)
        if hid == 0x0001:
            vals = list(struct.unpack_from("<" + "Q" * (hlen // 8), extra, ep + 4))
            vi = 0
            if usize == 0xFFFFFFFF:
                usize, vi = vals[vi], vi + 1
            if csize == 0xFFFFFFFF:
                csize, vi = vals[vi], vi + 1
            if lfh_off == 0xFFFFFFFF:
                lfh_off, vi = vals[vi], vi + 1
            break
        ep += 4 + hlen
    return usize, csize, lfh_off


def fetch_zip_member(spec: TraceSpec, out_dir: pathlib.Path) -> pathlib.Path:
    dst = out_dir / spec.local_name
    if verify_xz_file(dst):
        print(f"[skip] {spec.local_name} ({dst.stat().st_size / 1048576:.1f} MB)", flush=True)
        return dst

    tot = curl_head_size(spec.url)
    tail = curl_range(spec.url, max(0, tot - 65557), tot - 1, timeout=60)
    idx = tail.rfind(b"PK\x05\x06")
    _, _, _, _, n_entries, cd_size, cd_off, _ = struct.unpack_from("<4sHHHHIIH", tail, idx)
    if cd_off == 0xFFFFFFFF or n_entries == 0xFFFF:
        loc_idx = tail.rfind(b"PK\x06\x07")
        _, _, rel_off, _ = struct.unpack_from("<4sIQI", tail, loc_idx)
        eocd64 = curl_range(spec.url, rel_off, rel_off + 55, timeout=60)
        n_entries, cd_size, cd_off = struct.unpack_from("<QQQ", eocd64, 32)

    cd = curl_range(spec.url, cd_off, cd_off + cd_size - 1, timeout=120)
    pos = 0
    found = None
    for _ in range(n_entries):
        _, _, _, _, method, _, _, _, csize, usize, fn_len, ex_len, cm_len, _, _, _, lfh_off = struct.unpack_from("<4sHHHHHHIIIHHHHHII", cd, pos)
        pos += 46
        name = cd[pos:pos + fn_len].decode("utf-8", "ignore")
        extra = cd[pos + fn_len:pos + fn_len + ex_len]
        pos += fn_len + ex_len + cm_len
        usize, csize, lfh_off = _parse_zip64_extras(extra, usize, csize, lfh_off)
        if name == spec.member:
            found = (method, csize, usize, lfh_off)
            break
    if not found:
        raise KeyError(f"Member {spec.member} not found in {spec.url}")

    method, csize, usize, lfh_off = found
    lfh = curl_range(spec.url, lfh_off, lfh_off + 29, timeout=60)
    _, _, _, _, _, _, _, _, _, fn2, ex2 = struct.unpack_from("<4sHHHHHIIIHH", lfh, 0)
    data_start = lfh_off + 30 + fn2 + ex2
    comp_tmp = out_dir / (spec.local_name + ".comp.part")
    part = out_dir / (spec.local_name + ".part")
    print(f"[get]  {spec.local_name} (zip csize={csize / 1048576:.1f} MB)", flush=True)
    curl_range_to_file(spec.url, data_start, data_start + csize - 1, comp_tmp, timeout=1800)

    if method == 0:
        comp_tmp.replace(part)
    elif method == 8:
        dec = zlib.decompressobj(-zlib.MAX_WBITS)
        with comp_tmp.open("rb") as fi, part.open("wb") as fo:
            while chunk := fi.read(4 * 1048576):
                fo.write(dec.decompress(chunk))
            fo.write(dec.flush())
        comp_tmp.unlink(missing_ok=True)
    else:
        raise RuntimeError(f"Unsupported ZIP method {method} for {spec.member}")

    if not verify_xz_file(part) or part.stat().st_size != usize:
        raise RuntimeError(f"ZIP verify failed for {spec.local_name}: got {part.stat().st_size}, expect {usize}")
    part.replace(dst)
    print(f"[ok]   {spec.local_name} ({dst.stat().st_size / 1048576:.1f} MB)", flush=True)
    return dst


def fetch_tar_group(specs: list[TraceSpec], out_dir: pathlib.Path, max_scan: int = 200) -> list[pathlib.Path]:
    """Scan a single TAR URL via Range headers and extract all missing specs in one pass."""
    todo = {}
    done = []
    for sp in specs:
        dst = out_dir / sp.local_name
        if verify_xz_file(dst):
            print(f"[skip] {sp.local_name} ({dst.stat().st_size / 1048576:.1f} MB)", flush=True)
            done.append(dst)
        else:
            todo[sp.member] = sp
    if not todo:
        return done

    url = specs[0].url
    off = 0
    for _ in range(max_scan):
        if not todo:
            break
        hdr = curl_range(url, off, off + 511, timeout=60)
        if not hdr or hdr == b"\x00" * 512:
            break
        name = hdr[:100].split(b"\x00", 1)[0].decode("utf-8", "ignore")
        prefix = hdr[345:500].split(b"\x00", 1)[0].decode("utf-8", "ignore")
        if prefix:
            name = f"{prefix}/{name}"
        sz_s = hdr[124:136].split(b"\x00", 1)[0].strip()
        sz = int(sz_s, 8) if sz_s else 0
        if name in todo:
            sp = todo.pop(name)
            dst = out_dir / sp.local_name
            part = out_dir / (sp.local_name + ".part")
            print(f"[get]  {sp.local_name} (tar sz={sz / 1048576:.1f} MB @ {off})", flush=True)
            curl_range_to_file(url, off + 512, off + 512 + sz - 1, part, timeout=1800)
            if not verify_xz_file(part):
                raise RuntimeError(f"XZ magic check failed on {sp.local_name}")
            part.replace(dst)
            print(f"[ok]   {sp.local_name} ({dst.stat().st_size / 1048576:.1f} MB)", flush=True)
            done.append(dst)
        off += 512 + ((sz + 511) // 512) * 512

    if todo:
        raise RuntimeError(f"Unfound TAR entries after {max_scan} headers: {list(todo.keys())}")
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=("all", "dpc3_6xx", "zenodo_gap_xs", "zenodo_cvp1", "zenodo_qualcomm"), default="all")
    ap.add_argument("--files", nargs="*", default=None, help="Optional subset of trace filenames or stems to fetch")
    ap.add_argument("--out", type=pathlib.Path, default=OUT_DIR)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    selected = [t for t in TRACES if args.suite in ("all", t.suite)]
    if args.files:
        want = {f if f.endswith(".champsimtrace.xz") else f"{f}.champsimtrace.xz" for f in args.files}
        selected = [t for t in selected if t.local_name in want]
    if args.list:
        for t in selected:
            print(f"{t.suite:16s} {t.kind:6s} {t.local_name}")
        print(f"Total: {len(selected)} traces")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    # Schedule Zenodo zip/tar before throttled DPC-3 direct jobs so _DPC3_SEM never blocks Zenodo
    zips = [t for t in selected if t.kind == "zip"]
    directs = [t for t in selected if t.kind == "direct"]
    tar_by_url: dict[str, list[TraceSpec]] = {}
    for t in selected:
        if t.kind == "tar":
            tar_by_url.setdefault(t.url, []).append(t)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_zip_member, sp, args.out) for sp in zips]
        futs += [ex.submit(fetch_tar_group, url_specs, args.out) for url_specs in tar_by_url.values()]
        futs += [ex.submit(fetch_direct, sp, args.out) for sp in directs]
        for fut in as_completed(futs):
            fut.result()

    print(f"\nAll {len(selected)} traces verified in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
