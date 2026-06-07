"""Unit tests for voice / resolution / output helpers."""
import pytest
from pathlib import Path
from text_to_video import (
    VOICE_PRESETS, voice_short_label, resolve_voice,
    parse_resolutions, RESOLUTION_PRESETS,
    default_output_basename, resolve_output_folder,
    VIDEO_DIR,
)


def test_voice_preset_key_passthrough():
    assert voice_short_label("xiaoxiao") == "xiaoxiao"
    assert voice_short_label("aria") == "aria"


def test_voice_full_name_to_preset_key():
    # Full edge-tts names mapped to short preset keys.
    assert voice_short_label("zh-CN-XiaoxiaoNeural") == "xiaoxiao"
    assert voice_short_label("en-US-AriaNeural") == "aria"
    assert voice_short_label("en-US-AvaMultilingualNeural") == "ava-ml"


def test_voice_unknown_voice_strips_locale_and_suffix():
    # Unknown to presets: strip "xx-YY-" prefix and "Neural" / "MultilingualNeural" suffix.
    assert voice_short_label("en-US-XyzNeural") == "xyz"
    assert voice_short_label("zh-CN-SomeMultilingualNeural") == "some"


def test_voice_passthrough_completely_custom():
    assert voice_short_label("completely-custom-voice") == "completely-custom-voice"


def test_resolve_voice_key():
    assert resolve_voice("xiaoxiao") == "zh-CN-XiaoxiaoNeural"
    assert resolve_voice("aria") == "en-US-AriaNeural"


def test_resolve_voice_passthrough():
    # Full name not in presets passes through unchanged.
    assert resolve_voice("zh-CN-XiaomengNeural") == "zh-CN-XiaomengNeural"


def test_parse_resolutions_single_preset():
    out = parse_resolutions("720p")
    assert out == [("720p", 1280, 720)]


def test_parse_resolutions_csv():
    out = parse_resolutions("720p,1080p,square-720")
    keys = [k for k, _, _ in out]
    assert keys == ["720p", "1080p", "square-720"]


def test_parse_resolutions_all():
    out = parse_resolutions("all")
    assert len(out) == len(RESOLUTION_PRESETS)


def test_parse_resolutions_custom_wxh():
    out = parse_resolutions("1600x900")
    assert out == [("1600x900", 1600, 900)]


def test_parse_resolutions_dedupe():
    out = parse_resolutions("720p,720p,1080p")
    keys = [k for k, _, _ in out]
    assert keys == ["720p", "1080p"]


def test_parse_resolutions_empty_raises():
    with pytest.raises(SystemExit):
        parse_resolutions("")
    with pytest.raises(SystemExit):
        parse_resolutions(",,")


def test_parse_resolutions_invalid_raises():
    with pytest.raises(SystemExit):
        parse_resolutions("foo")


def test_default_output_basename_format():
    base = default_output_basename("sample.txt")
    # ends with _sample, starts with date pattern
    assert base.endswith("_sample")
    assert base[0:4].isdigit()  # year


def test_default_output_basename_for_text_input():
    base = default_output_basename("")
    assert base.endswith("_text")


def test_resolve_output_folder_bare_name():
    out = resolve_output_folder(Path("foo"), "default")
    assert out == VIDEO_DIR / "foo"


def test_resolve_output_folder_strips_mp4():
    out = resolve_output_folder(Path("foo.mp4"), "default")
    assert out == VIDEO_DIR / "foo"


def test_resolve_output_folder_absolute_path():
    out = resolve_output_folder(Path("/tmp/myproj.mp4"), "default")
    assert out == Path("/tmp/myproj")


def test_resolve_output_folder_none_uses_default():
    out = resolve_output_folder(None, "default-name")
    assert out == VIDEO_DIR / "default-name"
