"""
agent/encoding.py -- ensure UTF-8 stdio on Windows.

Call ``ensure_utf8_stdio()`` early in every CLI entry point so that
Unicode output (streaming model text, box-drawing scorecard, CJK
characters, etc.) does not raise ``UnicodeEncodeError`` on Windows
terminals whose default code page is not 65001.

On non-Windows platforms this is a no-op.
"""

from __future__ import annotations

import io
import os
import sys


def ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows.

    Three complementary steps:
    1. Set ``PYTHONUTF8=1`` so child processes also default to UTF-8.
    2. Call ``ctypes.windll.kernel32.SetConsoleOutputCP(65001)`` — the
       programmatic equivalent of ``chcp 65001``.
    3. ``sys.stdout.reconfigure(encoding="utf-8", errors="replace")`` so
       the *current* process writes UTF-8 with graceful fallback.

    Safe to call multiple times; skipped entirely on non-Windows.
    """
    if sys.platform != "win32":
        return

    # 1. Env flag for child processes (subprocess, py launcher, etc.)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    # 2. Console output code page → UTF-8
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass  # non-fatal: not a real console (e.g. piped output)

    # 3. Reconfigure the Python-level text streams
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        elif hasattr(stream, "encoding") and stream.encoding != "utf-8":
            # Fallback for wrapped streams that lack reconfigure()
            try:
                binary = getattr(stream, "buffer", None)
                if binary:
                    wrapper = io.TextIOWrapper(
                        binary, encoding="utf-8", errors="replace", line_buffering=True,
                    )
                    setattr(sys, stream_name, wrapper)
            except Exception:
                pass
