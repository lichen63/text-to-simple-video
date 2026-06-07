# Tests

Unit tests use pytest and run fast (no network, no ffmpeg invocation):

```bash
pip install -e ".[dev]"   # adds pytest
pytest                    # runs tests/test_*.py
```

What's covered:

- `test_split.py` — Chinese / English / mixed sentence splitting
- `test_wrap.py` — word-aware text wrapping
- `test_helpers.py` — voice/resolution parsing, output folder logic

End-to-end + interactive tests (require network for edge-tts, real ffmpeg
invocation, and a TTY) are not included in pytest. They live as standalone
runners in the maintainer's session workspace and can be added here later
if needed.
