"""Turn a chunk of Chinese text into a simple narrated video.

Per sentence:
  1. edge-tts -> mp3 (probe duration with ffprobe)
  2. Pillow renders the sentence to a PNG (auto-wrap, centered, black bg)
  3. ffmpeg combines PNG + MP3 into a clip (clip dur = audio + tail_silence)

ffmpeg concat demuxer stitches every clip into one mp4.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import edge_tts
from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parent
TEXT_DIR = REPO_ROOT / "text"
VIDEO_DIR = REPO_ROOT / "video"
FONTS_DIR = REPO_ROOT / "fonts"


# ---------- presets ----------

VOICE_PRESETS = {
    # 普通话 zh-CN
    "xiaoxiao":  ("zh-CN-XiaoxiaoNeural",          "普通话·女·亲切自然"),
    "xiaoyi":    ("zh-CN-XiaoyiNeural",            "普通话·女·活泼甜美"),
    "yunxi":     ("zh-CN-YunxiNeural",             "普通话·男·年轻阳光"),
    "yunxia":    ("zh-CN-YunxiaNeural",            "普通话·男·萌系少年"),
    "yunyang":   ("zh-CN-YunyangNeural",           "普通话·男·新闻播报"),
    "yunjian":   ("zh-CN-YunjianNeural",           "普通话·男·热情有力"),
    # 方言 zh-CN-*
    "xiaobei":   ("zh-CN-liaoning-XiaobeiNeural",  "辽宁话·女·幽默"),
    "xiaoni":    ("zh-CN-shaanxi-XiaoniNeural",    "陕西话·女·明亮"),
    # 粤语 zh-HK
    "hiugaai":   ("zh-HK-HiuGaaiNeural",           "粤语·女·友好"),
    "hiumaan":   ("zh-HK-HiuMaanNeural",           "粤语·女·亲和"),
    "wanlung":   ("zh-HK-WanLungNeural",           "粤语·男·友好"),
    # 台湾国语 zh-TW
    "hsiaochen": ("zh-TW-HsiaoChenNeural",         "台湾国语·女·友好"),
    "hsiaoyu":   ("zh-TW-HsiaoYuNeural",           "台湾国语·女·亲和"),
    "yunjhe":    ("zh-TW-YunJheNeural",            "台湾国语·男·友好"),
    # 多语言（中英混杂首选）
    "ava-ml":    ("en-US-AvaMultilingualNeural",     "多语言·女·亲切·中英混杂流畅"),
    "andrew-ml": ("en-US-AndrewMultilingualNeural",  "多语言·男·稳健·中英混杂流畅"),
    # 英文·美式
    "aria":      ("en-US-AriaNeural",              "英文·美式·女·自然"),
    "guy":       ("en-US-GuyNeural",               "英文·美式·男·热情"),
    "jenny":     ("en-US-JennyNeural",             "英文·美式·女·友好"),
    # 英文·英式
    "sonia":     ("en-GB-SoniaNeural",             "英文·英式·女"),
    "ryan":      ("en-GB-RyanNeural",              "英文·英式·男"),
}
DEFAULT_VOICE_KEY = "xiaoxiao"

RESOLUTION_PRESETS = {
    # 横屏 16:9
    "720p":          (1280,  720, "横屏·720p"),
    "1080p":         (1920, 1080, "横屏·1080p"),
    "1440p":         (2560, 1440, "横屏·1440p"),
    "4k":            (3840, 2160, "横屏·4K"),
    # 竖屏 9:16（抖音 / 视频号 / Reels）
    "vertical-720":  (720,  1280, "竖屏·720×1280"),
    "vertical-1080": (1080, 1920, "竖屏·1080×1920"),
    # 方屏 1:1（朋友圈 / Instagram）
    "square-720":    (720,   720, "方屏·720×720"),
    "square-1080":   (1080, 1080, "方屏·1080×1080"),
}
DEFAULT_RESOLUTION_KEY = "720p"

# Default font: tried in order, first that exists wins. Edit to taste.
DEFAULT_FONT_KEYS = [
    "bundled-sourcehansanscn-regular",  # cross-platform, modern (preferred)
    "bundled-lxgwwenkai-regular",       # cross-platform kaiti
    "hiragino-w6",                       # macOS fallback, sharp + bold
    "heiti-medium",
]

# Built-in macOS system fonts (cannot be redistributed; only used if present).
SYSTEM_FONT_PRESETS = [
    ("hiragino-w6",   "Hiragino W6 (粗黑体)",  "/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
    ("hiragino-w3",   "Hiragino W3 (常规黑)",   "/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("heiti-medium",  "STHeiti Medium",          "/System/Library/Fonts/STHeiti Medium.ttc",   1),
    ("heiti-light",   "STHeiti Light",           "/System/Library/Fonts/STHeiti Light.ttc",    1),
    ("songti-black",  "Songti Black (海报粗宋)",  "/System/Library/Fonts/Supplemental/Songti.ttc", 0),
    ("songti-bold",   "Songti Bold",             "/System/Library/Fonts/Supplemental/Songti.ttc", 1),
    ("songti-light",  "Songti Light",            "/System/Library/Fonts/Supplemental/Songti.ttc", 3),
    ("songti-regular", "Songti Regular",         "/System/Library/Fonts/Supplemental/Songti.ttc", 6),
]

# Friendly names for known open-source font filenames in fonts/.
BUNDLED_FONT_LABELS = {
    "LXGWWenKai-Regular.ttf":     "霞鹜文楷 (LXGW WenKai · 楷体)",
    "LXGWWenKai-Light.ttf":       "霞鹜文楷 Light",
    "LXGWWenKai-Medium.ttf":      "霞鹜文楷 Medium",
    "SourceHanSansCN-Regular.otf":  "思源黑体 SC Regular",
    "SourceHanSerifCN-Regular.otf": "思源宋体 SC Regular",
}


@dataclass
class FontChoice:
    key: str
    label: str
    path: str
    index: int = 0


# Sentence-ending punctuation. Comma-like marks stay in-sentence for natural TTS pauses.
# Sentence-ending punctuation. Chinese marks always split; English `.` only
# splits when followed by whitespace + capital letter (or end of text), to
# avoid breaking common abbreviations like "U.S." or numbers like "3.14".
SENTENCE_END_RE = re.compile(
    r"("
    r"[。！？；…]+"               # Chinese end punctuation
    r"|[!?;]+(?=\s|$)"            # English ! ? ; before whitespace/end
    r"|\.+(?=\s+[A-Z\u3400-\u9fff]|\s*$)"      # English . before \s+(CapLetter|CJK) or end
    r"|\n{2,}"                    # paragraph break
    r")"
)
SOFT_BREAK_RE = re.compile(r"[，,、]")


# ---------- text splitting ----------

def split_sentences(text: str, max_chars: int = 80) -> List[str]:
    text = text.strip()
    if not text:
        return []
    pieces: List[str] = []
    buf = ""
    for part in SENTENCE_END_RE.split(text):
        if not part:
            continue
        if SENTENCE_END_RE.fullmatch(part):
            if not part.startswith("\n"):
                buf += part
            if buf.strip():
                pieces.append(buf.strip())
            buf = ""
        else:
            buf += part
    if buf.strip():
        pieces.append(buf.strip())

    result: List[str] = []
    for piece in pieces:
        if len(piece) <= max_chars:
            result.append(piece)
            continue
        chunks: List[str] = []
        start = 0
        last_break = -1
        for m in SOFT_BREAK_RE.finditer(piece):
            if m.end() - start >= max_chars and last_break > start:
                chunks.append(piece[start:last_break + 1].strip())
                start = last_break + 1
            last_break = m.end() - 1
        tail = piece[start:].strip()
        if tail:
            chunks.append(tail)
        result.extend(c for c in chunks if c)
    return [s for s in result if s.strip()]


# ---------- TTS ----------

async def _tts_save(text: str, voice: str, rate: str, volume: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume)
    await communicate.save(str(out_path))


def synthesize(text: str, voice: str, rate: str, volume: str, out_path: Path) -> float:
    try:
        asyncio.run(_tts_save(text, voice, rate, volume, out_path))
    except ValueError as e:
        raise SystemExit(f"edge-tts 拒绝请求：{e}  "
                         f"用 `t2sv --list-voices` 查可用语音；rate/volume 形如 +0% / -10%。") from e
    return probe_duration(out_path)


def probe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ])
    return float(out.strip())


# ---------- image rendering ----------

def _load_font(path: str, size: int, index: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size, index=index)


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x3000 <= cp <= 0x303F     # CJK Symbols & Punctuation
        or 0x3400 <= cp <= 0x4DBF  # CJK Ext-A
        or 0x4E00 <= cp <= 0x9FFF  # CJK Unified Ideographs
        or 0xF900 <= cp <= 0xFAFF  # CJK Compatibility Ideographs
        or 0xFF00 <= cp <= 0xFFEF  # Halfwidth/Fullwidth Forms
    )


def _tokenize(text: str) -> List[Tuple[str, str]]:
    """Tokenise text into wrap units: CJK chars are individual, Latin words are atomic."""
    tokens: List[Tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            tokens.append(("NL", "\n"))
            i += 1
        elif ch.isspace():
            j = i
            while j < n and text[j].isspace() and text[j] != "\n":
                j += 1
            tokens.append(("SP", " "))
            i = j
        elif _is_cjk(ch):
            tokens.append(("CJK", ch))
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and not _is_cjk(text[j]):
                j += 1
            tokens.append(("WORD", text[i:j]))
            i = j
    return tokens


def _hard_break(word: str, font: ImageFont.FreeTypeFont, max_width: int) -> Tuple[List[str], str]:
    """Char-by-char break of an over-long token; returns (full_lines, trailing_partial)."""
    lines: List[str] = []
    current = ""
    for ch in word:
        trial = current + ch
        if current and font.getlength(trial) > max_width:
            lines.append(current)
            current = ch
        else:
            current = trial
    return lines, current


def _wrap_mixed(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Word-aware wrap for Latin runs, character-wise wrap for CJK."""
    lines: List[str] = []
    current = ""
    for kind, val in _tokenize(text):
        if kind == "NL":
            lines.append(current.rstrip())
            current = ""
        elif kind == "SP":
            if not current:
                continue  # drop leading space on a fresh line
            trial = current + val
            if font.getlength(trial) > max_width:
                lines.append(current.rstrip())
                current = ""
            else:
                current = trial
        elif kind == "CJK":
            trial = current + val
            if current and font.getlength(trial) > max_width:
                lines.append(current.rstrip())
                current = val
            else:
                current = trial
        else:  # WORD
            trial = current + val
            if current and font.getlength(trial) > max_width:
                lines.append(current.rstrip())
                current = val
            else:
                current = trial
            if font.getlength(current) > max_width:
                broken, current = _hard_break(current, font, max_width)
                lines.extend(broken)
    if current:
        lines.append(current.rstrip())
    return lines


def render_text_image(
    text: str,
    width: int,
    height: int,
    font: FontChoice,
    base_size: int,
    out_path: Path,
    max_lines: int = 6,
    margin_ratio: float = 0.08,
) -> Path:
    margin_x = int(width * margin_ratio)
    margin_y = int(height * margin_ratio)
    usable_w = width - 2 * margin_x
    usable_h = height - 2 * margin_y

    size = base_size
    while True:
        f = _load_font(font.path, size, font.index)
        lines = _wrap_mixed(text, f, usable_w)
        ascent, descent = f.getmetrics()
        line_h = ascent + descent
        line_spacing = int(line_h * 0.35)
        block_h = line_h * len(lines) + line_spacing * (len(lines) - 1)
        if (len(lines) <= max_lines and block_h <= usable_h) or size <= 18:
            break
        size = max(18, size - 4)

    img = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    y = (height - block_h) // 2
    for line in lines:
        line_w = f.getlength(line)
        x = (width - line_w) // 2
        draw.text((x, y), line, font=f, fill=(255, 255, 255))
        y += line_h + line_spacing
    img.save(out_path, format="PNG")
    return out_path


# ---------- ffmpeg ----------

def build_clip(image: Path, audio: Path, tail_silence: float, fps: int,
               width: int, height: int, out_path: Path) -> Path:
    audio_dur = probe_duration(audio)
    total = audio_dur + max(0.0, tail_silence)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image),
        "-i", str(audio),
        "-f", "lavfi", "-t", f"{tail_silence:.3f}", "-i", "anullsrc=r=24000:cl=mono",
        "-filter_complex", "[1:a][2:a]concat=n=2:v=0:a=1[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-crf", "18", "-preset", "medium",
        "-r", str(fps),
        "-vf", f"scale={width}:{height}:flags=lanczos,format=yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "24000", "-ac", "1",
        "-shortest", "-t", f"{total:.3f}",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def concat_clips(clips: List[Path], out_path: Path, work_dir: Path) -> Path:
    list_file = work_dir / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{c.resolve()}'" for c in clips) + "\n",
        encoding="utf-8",
    )
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy",
        str(out_path),
    ], check=True)
    return out_path


# ---------- font discovery ----------

def discover_fonts() -> List[FontChoice]:
    """System presets that exist + every font dropped into fonts/."""
    choices: List[FontChoice] = []

    for key, label, path, idx in SYSTEM_FONT_PRESETS:
        if Path(path).exists():
            choices.append(FontChoice(key=key, label=label, path=path, index=idx))

    if FONTS_DIR.exists():
        for f in sorted(FONTS_DIR.iterdir()):
            if f.suffix.lower() not in (".ttf", ".ttc", ".otf"):
                continue
            label = BUNDLED_FONT_LABELS.get(f.name, f.stem)
            key = "bundled-" + re.sub(r"[^A-Za-z0-9]+", "-", f.stem).strip("-").lower()
            choices.append(FontChoice(key=key, label=f"{label} (bundled)", path=str(f), index=0))

    return choices


def pick_default_font_index(fonts: List[FontChoice]) -> int:
    """Honour DEFAULT_FONT_KEYS priority; fall back to first available."""
    for key in DEFAULT_FONT_KEYS:
        for i, c in enumerate(fonts):
            if c.key == key:
                return i
    return 0


def resolve_font(value: Optional[str], discovered: List[FontChoice]) -> FontChoice:
    if value:
        for c in discovered:
            if c.key == value:
                return c
        p = Path(value)
        if p.exists():
            label = BUNDLED_FONT_LABELS.get(p.name, p.stem)
            return FontChoice(key="custom", label=f"{label} (custom)", path=str(p), index=0)
        raise SystemExit(f"--font: 没找到 '{value}'（既不是预设 key 也不是有效路径）")
    if not discovered:
        raise SystemExit("没有可用字体。请运行 `python fonts/download_fonts.py` 或用 --font 指定路径。")
    return discovered[pick_default_font_index(discovered)]


# ---------- prompts ----------

def _read_line_with_countdown(prompt_prefix: str, timeout: float) -> Optional[str]:
    """Show a live countdown; return the typed line, or None on timeout."""
    end = time.time() + timeout
    last_remaining = -1
    if not sys.stdin.isatty():
        return None
    while True:
        remaining = max(0, int(round(end - time.time())))
        if remaining != last_remaining:
            sys.stdout.write(f"\r{prompt_prefix} (自动选默认 {remaining:>2}s): ")
            sys.stdout.flush()
            last_remaining = remaining
        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
        if ready:
            line = sys.stdin.readline().rstrip("\n").strip()
            return line
        if end - time.time() <= 0:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return None


def prompt_choice(title: str, options: List[Tuple[str, str]], default_index: int,
                  timeout: float) -> int:
    """Render a numbered menu, accept index input (1-based) with timeout default."""
    print(f"\n── {title} ──")
    for i, (key, label) in enumerate(options, 1):
        marker = "★" if i - 1 == default_index else " "
        print(f"  {marker} {i}. {label}  [{key}]")
    line = _read_line_with_countdown(
        f"输入 1-{len(options)}，或回车用默认 ★{default_index + 1}",
        timeout,
    )
    if line is None or line == "":
        print(f"  → 用默认：{options[default_index][1]}")
        return default_index
    try:
        n = int(line)
        if 1 <= n <= len(options):
            print(f"  → 选择：{options[n-1][1]}")
            return n - 1
    except ValueError:
        pass
    print(f"  → 无效输入，用默认：{options[default_index][1]}")
    return default_index


def _parse_indices(line: str, count: int) -> Optional[List[int]]:
    """Parse '1,3,5' / '1 3 5' / '1-3' / 'all'. Return None on any invalid token."""
    line = line.strip()
    if not line:
        return []
    if line.lower() in ("*", "all"):
        return list(range(count))
    out: List[int] = []
    for part in re.split(r"[,\s]+", line):
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                return None
            if not (1 <= lo <= count and 1 <= hi <= count and lo <= hi):
                return None
            out.extend(range(lo - 1, hi))
            continue
        try:
            n = int(part)
        except ValueError:
            return None
        if not (1 <= n <= count):
            return None
        out.append(n - 1)
    # dedupe preserving order
    seen, ret = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            ret.append(x)
    return ret


def prompt_multi_choice(title: str, options: List[Tuple[str, str]],
                        default_indices: List[int], timeout: float) -> List[int]:
    """Multi-select menu. Accepts: '1,3' / '1 3' / '1-3' / 'all' / empty (default)."""
    print(f"\n── {title}  (多选: 1,3 或 1-3 或 all) ──")
    default_set = set(default_indices)
    for i, (key, label) in enumerate(options, 1):
        marker = "★" if i - 1 in default_set else " "
        print(f"  {marker} {i}. {label}  [{key}]")
    line = _read_line_with_countdown(
        f"输入选项 (e.g. 1,2,{len(options)})，或回车用默认 ★{','.join(str(i+1) for i in default_indices)}",
        timeout,
    )
    if line is None or line == "":
        labels = ", ".join(options[i][1] for i in default_indices)
        print(f"  → 用默认：{labels}")
        return list(default_indices)
    parsed = _parse_indices(line, len(options))
    if not parsed:
        labels = ", ".join(options[i][1] for i in default_indices)
        print(f"  → 无效输入，用默认：{labels}")
        return list(default_indices)
    labels = ", ".join(options[i][1] for i in parsed)
    print(f"  → 选择 {len(parsed)} 个：{labels}")
    return parsed


def prompt_text(title: str, default: str, timeout: float) -> str:
    print(f"\n── {title} ──")
    print(f"  默认: {default}")
    line = _read_line_with_countdown("输入新值或回车用默认", timeout)
    if line is None or line == "":
        print(f"  → 用默认：{default}")
        return default
    print(f"  → 使用：{line}")
    return line


# ---------- input / output resolution ----------

def resolve_input(value: Optional[Path]) -> Path:
    """Find an input file. Bare names try text/ first, then cwd."""
    if value is None:
        raise SystemExit("缺少输入文件，请传入路径或 --text \"...\"")
    if value.exists():
        return value
    in_text_dir = TEXT_DIR / value
    if in_text_dir.exists():
        return in_text_dir
    raise SystemExit(f"找不到输入文件: {value}（也试过了 {in_text_dir}）")


def default_output_basename(input_label: str) -> str:
    """The default base name shared by the project folder and inner mp4s."""
    stem = Path(input_label).stem if input_label else "text"
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M")
    return f"{ts}_{stem}"


def voice_short_label(voice_full_or_key: str) -> str:
    """Return a short, filename-safe label for a voice.

    If `voice_full_or_key` matches a preset key or full edge-tts ShortName,
    return the preset key. Otherwise strip locale prefix / `Neural` suffix.
    """
    if voice_full_or_key in VOICE_PRESETS:
        return voice_full_or_key
    for key, (full, _) in VOICE_PRESETS.items():
        if full == voice_full_or_key:
            return key
    s = re.sub(r"^[a-z]{2}-[A-Za-z]{2,}-(?:[a-z]+-)?", "", voice_full_or_key)
    s = re.sub(r"(Multilingual)?Neural$", "", s)
    return (s or voice_full_or_key).lower()


def resolve_output_folder(value: Optional[Path], default_basename: str) -> Path:
    """Decide the project folder path.

    - `value` is the user-supplied -o or prompt input.
    - .mp4 suffix is stripped (we always create a folder, not a single file).
    - Bare names (no parent) go under VIDEO_DIR.
    """
    if value is None:
        return VIDEO_DIR / default_basename
    p = value
    if p.suffix.lower() == ".mp4":
        p = p.parent / p.stem
    if not p.is_absolute() and p.parent == Path("."):
        p = VIDEO_DIR / p.name
    return p


# ---------- resolution / voice helpers ----------

def parse_resolutions(val: str) -> List[Tuple[str, int, int]]:
    """Parse one or more resolutions. Returns list of (key, w, h).

    Accepts: '720p' | '720p,1080p' | 'all' | '1600x900' | '720p,1280x720'
    """
    val = val.strip()
    if not val:
        raise SystemExit("--resolution 不能为空")
    if val.lower() in ("*", "all"):
        return [(k, w, h) for k, (w, h, _) in RESOLUTION_PRESETS.items()]
    out: List[Tuple[str, int, int]] = []
    seen = set()
    for part in re.split(r"[,\s]+", val):
        if not part:
            continue
        if part in RESOLUTION_PRESETS:
            w, h, _ = RESOLUTION_PRESETS[part]
            key = part
        else:
            m = re.fullmatch(r"(\d+)x(\d+)", part.lower())
            if not m:
                raise SystemExit(f"无法识别的分辨率: {part}")
            w, h = int(m.group(1)), int(m.group(2))
            key = f"{w}x{h}"
        if key not in seen:
            seen.add(key)
            out.append((key, w, h))
    if not out:
        raise SystemExit(f"--resolution {val!r} 解析后没有任何有效分辨率")
    return out


def resolve_voice(val: str) -> str:
    return VOICE_PRESETS[val][0] if val in VOICE_PRESETS else val


# ---------- orchestration ----------

def build_videos(text: str,
                 jobs: List[Tuple[str, int, int, Path]],
                 voice: str, rate: str, volume: str,
                 font: FontChoice, font_size: int,
                 tail_silence: float, fps: int, keep_temp: bool) -> List[Path]:
    """Render N videos from the same text+voice but different (w,h)/outputs.

    `jobs` is a list of (preset_key, width, height, output_path).
    TTS is performed once; per-resolution we only re-render images + ffmpeg clips.
    """
    sentences = split_sentences(text)
    if not sentences:
        raise SystemExit("切句后没有内容，输入是空的吗？")
    print(f"\n[+] 切出 {len(sentences)} 句")
    print(f"[+] 字体: {font.label}")
    print(f"[+] 语音: {voice}")
    print(f"[+] 待生成 {len(jobs)} 个视频:")
    for key, w, h, out in jobs:
        print(f"    · [{key}] {w}×{h}  ->  {out}")

    tmp_root = Path(tempfile.mkdtemp(prefix="t2sv_"))
    print(f"[+] 临时目录: {tmp_root}")
    try:
        # Phase 1: TTS once, shared across all output resolutions.
        print(f"\n[1/2] 合成语音 ({len(sentences)} 句)")
        audio_paths: List[Path] = []
        for i, sentence in enumerate(sentences, 1):
            preview = sentence if len(sentence) <= 30 else sentence[:30] + "…"
            print(f"  [{i}/{len(sentences)}] {preview}")
            audio = tmp_root / f"audio_{i:04d}.mp3"
            synthesize(sentence, voice, rate, volume, audio)
            audio_paths.append(audio)

        # Phase 2: per-resolution image render + ffmpeg pipeline.
        outputs: List[Path] = []
        for ji, (key, w, h, out_path) in enumerate(jobs, 1):
            print(f"\n[2/2] 渲染分辨率 {ji}/{len(jobs)}: [{key}] {w}×{h}")
            res_dir = tmp_root / f"r_{key}"
            res_dir.mkdir(exist_ok=True)
            clip_videos: List[Path] = []
            for i, (sentence, audio) in enumerate(zip(sentences, audio_paths), 1):
                image = res_dir / f"s{i:04d}.png"
                video = res_dir / f"s{i:04d}.mp4"
                render_text_image(sentence, w, h, font, font_size, image)
                build_clip(image, audio, tail_silence, fps, w, h, video)
                clip_videos.append(video)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            concat_clips(clip_videos, out_path, res_dir)
            outputs.append(out_path)
            print(f"    ✓ {out_path}")
        return outputs
    finally:
        if keep_temp:
            print(f"\n[+] 已保留临时文件: {tmp_root}")
        else:
            shutil.rmtree(tmp_root, ignore_errors=True)


# ---------- CLI ----------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="把一段中文文本生成黑底白字、edge-tts 朗读的简单视频。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("input", nargs="?", type=Path,
                     help="文本文件路径（裸文件名会先去 text/ 找）。")
    src.add_argument("--text", type=str, help="直接传一段文字。")

    p.add_argument("-o", "--output", type=Path,
                   help="项目名（在 video/ 下创建同名文件夹，里面放视频）。"
                        "默认 <时间>_<input-stem>。")
    p.add_argument("--voice",
                   help="语音预设 key (%s) 或完整 edge-tts 名。" % ", ".join(VOICE_PRESETS))
    p.add_argument("--rate", default="+0%",
                   help="TTS 语速，如 -10%% / +20%%（负数需用 = 写法：--rate=-10%%）。")
    p.add_argument("--volume", default="+0%",
                   help="TTS 音量，如 +0%% / -20%%（负数需用 = 写法：--volume=-20%%）。")
    p.add_argument("--resolution",
                   help="一个或多个分辨率：%s，或 WxH。多个用逗号/空格分隔，all 表示全部。"
                        % " / ".join(RESOLUTION_PRESETS))
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--font", help="字体 key（运行时会列出可用项）或 .ttf/.ttc/.otf 路径。")
    p.add_argument("--font-size", type=int, default=64,
                   help="基础字号（自动随内容缩小）。")
    p.add_argument("--tail-silence", type=float, default=0.4,
                   help="每句朗读后的静音秒数（默认 0.4）。")
    p.add_argument("--fps", type=int, default=24, help="输出帧率（默认 24）。")
    p.add_argument("--list-voices", action="store_true",
                   help="列出所有可用语音预设并退出。")
    p.add_argument("--no-prompt", action="store_true",
                   help="跳过所有交互，缺省值都走默认。")
    p.add_argument("--prompt-timeout", type=float, default=10.0,
                   help="每个交互项的等待秒数（默认 10）。")
    p.add_argument("--keep-temp", action="store_true",
                   help="保留中间产物，调试用。")
    return p.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.list_voices:
        width = max(len(k) for k in VOICE_PRESETS)
        print(f"{'KEY':{width}}  {'描述':30}  EDGE-TTS 名称")
        print("-" * (width + 50))
        for key, (full, label) in VOICE_PRESETS.items():
            print(f"{key:{width}}  {label:30}  {full}")
        print(f"\n共 {len(VOICE_PRESETS)} 个预设。")
        print("用法示例：t2sv sample.txt --voice yunjian")
        return 0

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"`{tool}` 不在 PATH 里，请先安装。")

    # --- load text ---
    if args.text is not None:
        text = args.text
        input_label = "text"
    else:
        input_path = resolve_input(args.input)
        try:
            text = input_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise SystemExit(f"读 {input_path} 失败：内容不是 UTF-8 文本。{e}")
        input_label = input_path.name

    # --- discover fonts ---
    fonts = discover_fonts()
    if not fonts:
        print("⚠️  没扫到任何字体；请运行 `python fonts/download_fonts.py` 拉取开源字体。")

    interactive = not args.no_prompt and sys.stdin.isatty()
    timeout = max(1.0, args.prompt_timeout)

    # --- voice ---
    if args.voice:
        voice = resolve_voice(args.voice)
    else:
        keys = list(VOICE_PRESETS)
        default_idx = keys.index(DEFAULT_VOICE_KEY) if DEFAULT_VOICE_KEY in keys else 0
        if interactive:
            idx = prompt_choice(
                "选择语音 voice",
                [(k, f"{VOICE_PRESETS[k][1]}  ·  {VOICE_PRESETS[k][0]}") for k in keys],
                default_index=default_idx,
                timeout=timeout,
            )
        else:
            idx = default_idx
        voice = VOICE_PRESETS[keys[idx]][0]

    # --- resolution (multi-select) ---
    if args.width or args.height:
        if not (args.width and args.height):
            raise SystemExit("--width 和 --height 必须同时给。")
        resolutions: List[Tuple[str, int, int]] = [
            (f"{args.width}x{args.height}", args.width, args.height)
        ]
    elif args.resolution:
        resolutions = parse_resolutions(args.resolution)
    else:
        keys = list(RESOLUTION_PRESETS)
        default_idx = keys.index(DEFAULT_RESOLUTION_KEY) if DEFAULT_RESOLUTION_KEY in keys else 0
        if interactive:
            indices = prompt_multi_choice(
                "选择分辨率 resolution",
                [(k, RESOLUTION_PRESETS[k][2]) for k in keys],
                default_indices=[default_idx],
                timeout=timeout,
            )
        else:
            indices = [default_idx]
        resolutions = [(keys[i], RESOLUTION_PRESETS[keys[i]][0], RESOLUTION_PRESETS[keys[i]][1])
                       for i in indices]

    # --- font ---
    if args.font:
        font = resolve_font(args.font, fonts)
    elif interactive and fonts:
        default_idx = pick_default_font_index(fonts)
        idx = prompt_choice(
            "选择字体 font",
            [(c.key, c.label) for c in fonts],
            default_index=default_idx,
            timeout=timeout,
        )
        font = fonts[idx]
    else:
        font = resolve_font(None, fonts)

    # --- output folder + per-resolution filenames ---
    default_base = default_output_basename(input_label)
    if args.output:
        folder = resolve_output_folder(args.output, default_base)
    elif interactive:
        chosen = prompt_text(
            f"项目名（会在 {VIDEO_DIR.relative_to(REPO_ROOT)}/ 下建文件夹）",
            default_base,
            timeout,
        )
        folder = resolve_output_folder(Path(chosen), default_base)
    else:
        folder = resolve_output_folder(None, default_base)

    folder.mkdir(parents=True, exist_ok=True)
    vshort = voice_short_label(voice)
    outputs = [folder / f"{vshort}_{rkey}.mp4" for rkey, _, _ in resolutions]

    jobs: List[Tuple[str, int, int, Path]] = [
        (rkey, w, h, out_path)
        for (rkey, w, h), out_path in zip(resolutions, outputs)
    ]

    final = build_videos(
        text=text, jobs=jobs,
        voice=voice, rate=args.rate, volume=args.volume,
        font=font, font_size=args.font_size,
        tail_silence=args.tail_silence, fps=args.fps, keep_temp=args.keep_temp,
    )
    print(f"\n[✓] 完成 {len(final)} 个视频，输出到: {folder}/")
    for f in final:
        print(f"    {f.name}")
    return 0


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        print("\n[!] 已取消")
        return 130


if __name__ == "__main__":
    sys.exit(main())
