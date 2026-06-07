"""Unit tests for word-aware text wrapping."""
import pytest
from pathlib import Path
from PIL import ImageFont
from text_to_video import _wrap_mixed, _tokenize, _is_cjk

# Pick the first font that exists on the test machine.
CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _load_test_font(size: int = 48):
    for path in CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    pytest.skip("no CJK system font available for wrap tests")


def test_is_cjk():
    assert _is_cjk("中")
    assert _is_cjk("。")
    assert not _is_cjk("a")
    assert not _is_cjk(" ")
    assert not _is_cjk(".")


def test_tokenize_pure_english():
    toks = _tokenize("Hello world")
    kinds = [k for k, _ in toks]
    assert kinds == ["WORD", "SP", "WORD"]


def test_tokenize_pure_cjk():
    toks = _tokenize("你好")
    assert [k for k, _ in toks] == ["CJK", "CJK"]


def test_tokenize_mixed():
    toks = _tokenize("Hello 世界")
    assert [k for k, _ in toks] == ["WORD", "SP", "CJK", "CJK"]


def test_tokenize_collapses_whitespace():
    toks = _tokenize("a    b")
    spaces = [v for k, v in toks if k == "SP"]
    assert spaces == [" "]


def test_tokenize_newline():
    toks = _tokenize("a\nb")
    kinds = [k for k, _ in toks]
    assert "NL" in kinds


def test_wrap_english_words_not_split():
    font = _load_test_font(48)
    # narrow line; force wrap. Each word must stay intact.
    lines = _wrap_mixed("Hello world this is Python", font, 200)
    rejoined = " ".join(lines)
    # words after rejoin must match originals; no mid-word breaks
    assert "Hello" in rejoined and "world" in rejoined
    assert "Python" in rejoined
    for w in ("Hello", "world", "this", "Python"):
        assert any(w == part for line in lines for part in line.split())


def test_wrap_chinese_per_char():
    font = _load_test_font(48)
    lines = _wrap_mixed("中文逐字换行的测试", font, 200)
    assert len(lines) >= 2


def test_wrap_super_long_word_hard_breaks():
    font = _load_test_font(48)
    word = "supercalifragilisticexpialidocious"
    lines = _wrap_mixed(word, font, 200)
    # The word must be broken into multiple lines.
    assert len(lines) >= 2
    # Joining all pieces back should give the original word.
    assert "".join(lines) == word


def test_wrap_mixed_cn_en():
    font = _load_test_font(48)
    lines = _wrap_mixed("我用 Python 写代码 today", font, 280)
    # English words still intact
    for w in ("Python", "today"):
        assert any(w == part for line in lines for part in line.split())


def test_wrap_explicit_newline():
    font = _load_test_font(48)
    lines = _wrap_mixed("Line one\nLine two", font, 9999)
    assert len(lines) == 2
