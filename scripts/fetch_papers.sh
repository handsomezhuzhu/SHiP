#!/usr/bin/env bash
# 下载 SHiP 方向(LLC 缓存替换/插入策略)可公开获取的论文 PDF
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/papers/pdf"
mkdir -p "$OUT"

fetch() {
  local name="$1" url="$2"
  [[ -s "$OUT/$name" ]] && { echo "skip  $name"; return; }
  echo "get   $name"
  curl -sL --retry 3 --retry-delay 2 --max-time 300 -o "$OUT/$name.part" "$url" \
    && mv "$OUT/$name.part" "$OUT/$name"
  if ! pdfinfo "$OUT/$name" >/dev/null 2>&1; then
    echo "FAIL  $name ($url)"; rm -f "$OUT/$name"; return
  fi
  echo "ok    $name  $(pdfinfo "$OUT/$name" | awk '/Pages/{print $2" pages"}')"
}

fetch ship_micro11.pdf            "https://mrmgroup.cs.princeton.edu/papers/MICRO11_SHiP_Wu_Final.pdf"
fetch perceptron_micro16.pdf     "https://people.engr.tamu.edu/djimenez/pdfs/micro2016-perceptron.pdf"
fetch mpppb_micro17.pdf          "https://people.engr.tamu.edu/djimenez/pdfs/p436-jimenez.pdf"
fetch hawkeye_isca17.pdf         "https://www.cs.utexas.edu/~lin/papers/isca17.pdf"
fetch hawkeye_crc17.pdf          "https://www.cs.utexas.edu/~lin/papers/crc17.pdf"
fetch glider_micro19.pdf         "https://www.cs.utexas.edu/~lin/papers/micro19c.pdf"
fetch mockingjay_hpca22.pdf      "https://www.cs.utexas.edu/~lin/papers/hpca22.pdf"
fetch belady_isca16.pdf          "https://www.cs.utexas.edu/~lin/papers/isca16.pdf"
fetch harmony_isca18.pdf         "https://www.cs.utexas.edu/~lin/papers/isca18.pdf"
fetch rlr_hpca21.pdf             "https://www.ece.umn.edu/users/jsartori/papers/hpca21.pdf"
fetch care_2023.pdf              "https://grc.iit.edu/papers/2023/lu-2023-care-bc99.pdf"
fetch llc_characterization_iiswc20.pdf "https://people.engr.tamu.edu/djimenez/pdfs/IISWC2020.pdf"
fetch mdpp_hpca16.pdf            "https://people.engr.tamu.edu/djimenez/pdfs/hpca2016-mdpp.pdf"
fetch cachefit_arxiv26.pdf       "https://arxiv.org/pdf/2610.10579"

# 基础/背景论文
fetch rrip_isca10.pdf            "http://www.jaleels.org/ajaleel/publications/isca2010-rrip.pdf"
fetch dip_isca07.pdf             "http://www.jaleels.org/ajaleel/publications/isca2007-dip.pdf"
fetch sdbp_micro10.pdf           "https://people.engr.tamu.edu/djimenez/pdfs/micro2010_sampler_dist.pdf"
fetch pacman_micro11.pdf         "http://www.jaleels.org/ajaleel/publications/micro2011-PACMan.pdf"
fetch champsim_arxiv22.pdf       "https://arxiv.org/pdf/2210.14324"

# CRC-2 (2017) 同场论文集（Dropbox）
fetch shipplusplus_crc17.pdf     "https://www.dropbox.com/s/algx6mwxa591uoy/Ship%2B%2B.pdf?dl=1"
fetch harmony_crc17.pdf          "https://www.dropbox.com/s/xx1vnvcrarpfq1b/Less%20is%20More.pdf?dl=1"
fetch mpppb_crc17.pdf            "https://www.dropbox.com/s/jddnsi5letvo2p5/Multiperspective.pdf?dl=1"
fetch expected_hit_count_crc17.pdf "https://www.dropbox.com/s/z685pmu1mn2lgr1/Expected%20Hit%20Count.pdf?dl=1"
fetch red_crc17.pdf              "https://www.dropbox.com/s/4iiosztjzr008z7/ReD.pdf?dl=1"
fetch hawkeye_crc17_slides.pdf   "https://www.dropbox.com/s/7riayq24gssxq1j/crc17-hawkeye.pdf?dl=1"
