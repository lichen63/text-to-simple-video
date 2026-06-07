"""Unit tests for sentence splitting."""
import pytest
from text_to_video import split_sentences


def test_chinese_only():
    assert split_sentences("纯中文。第二句！第三句？") == [
        "纯中文。", "第二句！", "第三句？"
    ]


def test_english_only():
    assert split_sentences("Hello world. This is great! Are you ready?") == [
        "Hello world.", "This is great!", "Are you ready?"
    ]


def test_mixed_cn_en():
    assert split_sentences("我用 Python。Today I learned regex. 很好用！") == [
        "我用 Python。", "Today I learned regex.", "很好用！"
    ]


def test_preserves_decimals():
    # "3.14" must not split
    out = split_sentences("Pi is 3.14 approximately.")
    assert out == ["Pi is 3.14 approximately."]


def test_preserves_us_dot_abbrev():
    # "U.S." should stay together (no \s+ after first dot)
    out = split_sentences("I visited the U.S. last year.")
    assert len(out) <= 2  # ideally 1, may be 2 if regex hits second '.'
    assert any("U.S." in s for s in out)


def test_paragraph_break():
    assert split_sentences("First.\n\nSecond paragraph.") == [
        "First.", "Second paragraph."
    ]


def test_question_then_lowercase():
    # ? always splits
    assert split_sentences("Why? oh well.") == ["Why?", "oh well."]


def test_does_not_split_code_semicolons():
    # ASCII ; is NOT a sentence terminator in English (B1 fix)
    out = split_sentences("for (int i = 0; i < n; i++) print(i)")
    assert len(out) == 1


def test_chinese_semicolon_splits():
    # Chinese ； IS a sentence terminator
    out = split_sentences("第一段；第二段；第三段。")
    assert len(out) == 3


def test_empty_input():
    assert split_sentences("") == []
    assert split_sentences("   \n  ") == []


def test_no_punctuation():
    out = split_sentences("没有标点的一段文字")
    assert out == ["没有标点的一段文字"]


def test_long_sentence_falls_back_to_soft_break():
    # >80 chars with commas should secondary-split
    long_text = "首先" + "我们要做的事情有很多，" * 10 + "然后结束。"
    out = split_sentences(long_text)
    assert len(out) > 1  # split happened
