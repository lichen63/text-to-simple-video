"""Render a sample image for every detected font and save to examples/font-samples/.

Run any time to (re)generate the font preview gallery. Output filenames are
`<font-key>.png`, sorted by the same order the interactive menu shows.

    python examples/render_font_samples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from text_to_video import discover_fonts  # noqa: E402

SAMPLE_TEXT = "沿途的风景，远比终点更值得驻足。"
W, H = 1280, 220
OUT_DIR = REPO_ROOT / "examples" / "font-samples"


def main() -> int:
    fonts = discover_fonts()
    if not fonts:
        print("没扫到字体。先跑 `python fonts/download_fonts.py` 或在 macOS 上跑。", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in fonts:
        body = ImageFont.truetype(f.path, 72, index=f.index)
        label = ImageFont.truetype(f.path, 28, index=f.index)
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((20, 12), f.label, font=label, fill=(180, 180, 180))
        line_w = body.getlength(SAMPLE_TEXT)
        draw.text(((W - line_w) // 2, 90), SAMPLE_TEXT, font=body, fill=(255, 255, 255))
        out = OUT_DIR / f"{f.key}.png"
        img.save(out)
        print(f"  ✓ {out.relative_to(REPO_ROOT)}")
    print(f"\nRendered {len(fonts)} font samples to {OUT_DIR.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
