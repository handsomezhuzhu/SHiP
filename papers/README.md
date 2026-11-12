# papers/

论文 PDF 不入库（版权 + 体积）。重新获取：

```bash
./scripts/fetch_papers.sh
```

- 能公开下载的论文见 `manifest.tsv`，脚本会自动补齐缺失文件。
- 需要校园网/图书馆权限的论文见 `docs/papers.md` 的"待获取"一节。
- 下载后可以用 `pdfinfo` / `pdftotext` 校验是否完整。