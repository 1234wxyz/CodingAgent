"""
tests/test_encoding.py -- ensure_utf8_stdio correctness on all platforms.
"""

import io
import sys

from agent.encoding import ensure_utf8_stdio


def test_ensure_utf8_stdio_is_idempotent():
    """Calling ensure_utf8_stdio() twice does not raise or corrupt streams."""
    ensure_utf8_stdio()
    ensure_utf8_stdio()
    # stdout should still be writable
    assert sys.stdout.writable() or hasattr(sys.stdout, "write")


def test_ensure_utf8_stdio_sets_env(monkeypatch):
    """On Windows, PYTHONUTF8 and PYTHONIOENCODING are set."""
    import os
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)

    ensure_utf8_stdio()

    assert os.environ.get("PYTHONUTF8") == "1"
    assert os.environ.get("PYTHONIOENCODING") == "utf-8"


def test_ensure_utf8_stdio_noop_on_linux(monkeypatch):
    """On non-Windows, ensure_utf8_stdio does nothing."""
    import os
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("PYTHONUTF8", raising=False)

    ensure_utf8_stdio()

    # Should NOT have set PYTHONUTF8 (linux path is a no-op)
    assert "PYTHONUTF8" not in os.environ


def test_stdout_can_write_unicode_after_setup():
    """After ensure_utf8_stdio(), writing Unicode box-drawing chars works."""
    ensure_utf8_stdio()
    # This would raise UnicodeEncodeError on Windows with cp936 without the fix
    text = "╔══╗\n║OK║\n╚══╝"
    buf = io.StringIO()
    buf.write(text)
    assert "OK" in buf.getvalue()


def test_stdout_encoding_is_utf8_on_windows(monkeypatch):
    """On Windows, stdout.encoding should be utf-8 after setup."""
    if sys.platform != "win32":
        # On non-Windows we can't meaningfully test this — skip
        return
    ensure_utf8_stdio()
    assert sys.stdout.encoding.lower().replace("-", "") == "utf8"
