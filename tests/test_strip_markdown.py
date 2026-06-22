"""Unit tests for Markdown preprocessing (strip_markdown)."""
from text_to_video import strip_markdown, split_sentences


def test_front_matter_removed():
    md = "---\ntitle: Hello\ndate: 2026-01-01\npublished: false\n---\n正文第一句。"
    assert strip_markdown(md).strip() == "正文第一句。"


def test_front_matter_only_at_start():
    # A `---` later in the body is a horizontal rule, not front matter.
    md = "开头。\n\n---\n\n结尾。"
    assert strip_markdown(md).strip() == "开头。\n\n结尾。"


def test_heading_marker_removed():
    assert strip_markdown("## 标题").strip() == "标题"
    assert strip_markdown("#标题").strip() == "标题"  # no space (common CN habit)


def test_emphasis_unwrapped():
    assert strip_markdown("**粗** 和 *斜* 和 `码`").strip() == "粗 和 斜 和 码"
    assert strip_markdown("__重__ 与 ~~删~~").strip() == "重 与 删"


def test_link_to_text_and_image_dropped():
    assert strip_markdown("看[这里](http://x.com)吧。").strip() == "看这里吧。"
    assert strip_markdown("![alt](http://x.com/a.png)图。").strip() == "图。"


def test_list_markers_removed():
    md = "- 第一\n- 第二\n1. 甲\n2. 乙"
    assert strip_markdown(md).strip() == "第一\n第二\n甲\n乙"


def test_blockquote_removed():
    assert strip_markdown("> 引用一句。").strip() == "引用一句。"


def test_code_fence_removed():
    md = "前。\n```python\nprint(1)\n```\n后。"
    assert strip_markdown(md).strip() == "前。\n\n后。"


def test_html_comment_removed():
    assert strip_markdown("前<!-- 注释 -->后").strip() == "前后"


def test_hr_becomes_paragraph_break():
    assert strip_markdown("上。\n\n***\n\n下。").strip() == "上。\n\n下。"


def test_setext_h1_underline_removed():
    # `===` under a line is a setext H1 underline; must not survive as literal.
    assert strip_markdown("标题文字\n======\n\n正文。").strip() == "标题文字\n\n正文。"


def test_setext_h2_underline_removed():
    assert strip_markdown("标题文字\n------\n正文。").strip() == "标题文字\n\n正文。"


def test_closed_atx_heading_trailing_hashes_removed():
    assert strip_markdown("## 标题 ##").strip() == "标题"
    assert strip_markdown("# 标题 #").strip() == "标题"


def test_csharp_in_heading_preserved():
    # Trailing-# stripping requires whitespace before #, so 'C#' is safe.
    assert strip_markdown("# C#").strip() == "C#"


def test_chinese_dash_not_treated_as_hr():
    # 中文破折号 —— must survive (not an ASCII horizontal rule).
    assert "——" in strip_markdown("他说——你好。")


def test_snake_case_underscore_preserved():
    assert strip_markdown("变量 my_var_name 不变").strip() == "变量 my_var_name 不变"


def test_table_stripped():
    md = "| 名 | 值 |\n| --- | --- |\n| 甲 | 一 |"
    out = strip_markdown(md).strip()
    assert "|" not in out and "---" not in out
    assert "名" in out and "值" in out and "甲" in out and "一" in out


def test_integration_front_matter_heading_then_split():
    md = "---\ntitle: T\n---\n## 标题\n\n第一句。第二句！"
    assert split_sentences(strip_markdown(md)) == ["标题", "第一句。", "第二句！"]


def test_plain_text_is_unchanged():
    # No markdown -> identical content (modulo trailing newline).
    plain = "人生不是一场赛跑，而是一段旅程。沿途的风景，远比终点更值得驻足。"
    assert strip_markdown(plain).strip() == plain
