"""Fetch open-source CJK fonts into this directory.

Run after `git clone`:

    python fonts/download_fonts.py

Downloads (all SIL OFL 1.1, free for redistribution & embedding):
  * LXGW WenKai (霞鹜文楷)               — kaiti, ~24 MB
  * Source Han Sans CN Regular (思源黑体) — sans, ~10 MB after unzip
  * Source Han Serif CN Regular (思源宋体) — serif, ~10 MB after unzip

Existing files are kept; pass --force to redownload.

Slow from your network?  Try a GitHub mirror:

    python fonts/download_fonts.py --mirror https://gh-proxy.com/
    python fonts/download_fonts.py --mirror https://ghproxy.net/
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent

# Pinned versions. Bump these intentionally when you want fresher releases.
DOWNLOADS = [
    {
        "name": "LXGW WenKai (霞鹜文楷)",
        "url": "https://github.com/lxgw/LxgwWenKai/releases/download/v1.522/LXGWWenKai-Regular.ttf",
        "out": "LXGWWenKai-Regular.ttf",
        "kind": "raw",
    },
    {
        "name": "Source Han Sans CN (思源黑体)",
        "url": "https://github.com/adobe-fonts/source-han-sans/releases/download/2.005R/19_SourceHanSansCN.zip",
        "out": "SourceHanSansCN-Regular.otf",
        "kind": "zip",
        # path inside the zip to extract
        "zip_member_suffix": "SourceHanSansCN-Regular.otf",
    },
    {
        "name": "Source Han Serif CN (思源宋体)",
        "url": "https://github.com/adobe-fonts/source-han-serif/releases/download/2.003R/14_SourceHanSerifCN.zip",
        "out": "SourceHanSerifCN-Regular.otf",
        "kind": "zip",
        "zip_member_suffix": "SourceHanSerifCN-Regular.otf",
    },
]


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as resp, dest.open("wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        chunk = 64 * 1024
        read = 0
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            out.write(buf)
            read += len(buf)
            if total:
                pct = read * 100 / total
                sys.stdout.write(f"\r    {fmt_size(read)} / {fmt_size(total)} ({pct:.0f}%)")
            else:
                sys.stdout.write(f"\r    {fmt_size(read)}")
            sys.stdout.flush()
        sys.stdout.write("\n")


def extract_from_zip(zip_path: Path, suffix: str, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as z:
        match = next((n for n in z.namelist() if n.endswith(suffix)), None)
        if not match:
            raise RuntimeError(f"{suffix} not found inside {zip_path.name}")
        with z.open(match) as src, dest.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def fetch_one(spec: dict, force: bool, mirror: str) -> None:
    final = FONTS_DIR / spec["out"]
    if final.exists() and not force:
        print(f"[skip] {spec['name']}  (already at {final.name})")
        return
    print(f"[fetch] {spec['name']}")
    url = spec["url"]
    if mirror:
        url = mirror.rstrip("/") + "/" + url
    tmp_dir = Path(tempfile.mkdtemp(prefix="t2v_font_"))
    try:
        if spec["kind"] == "raw":
            download(url, final)
        else:
            zip_path = tmp_dir / "pkg.zip"
            download(url, zip_path)
            extract_from_zip(zip_path, spec["zip_member_suffix"], final)
        print(f"    -> {final}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--force", action="store_true", help="Redownload even if files exist.")
    parser.add_argument("--mirror", default="",
                        help="Prefix prepended to every GitHub URL "
                             "(e.g. https://gh-proxy.com/ for users in mainland China).")
    args = parser.parse_args()

    print(f"Target dir: {FONTS_DIR}")
    if args.mirror:
        print(f"Using mirror: {args.mirror}")
    for spec in DOWNLOADS:
        try:
            fetch_one(spec, args.force, args.mirror)
        except Exception as exc:
            print(f"    !! failed: {exc}", file=sys.stderr)
            return 1
    print("\nAll done. These fonts will be auto-detected by text_to_video.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
