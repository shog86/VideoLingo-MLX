"""Stream live terminal-style logs into the Streamlit UI.

Usage:
    log = UILog(st.empty(), title="Phase 1 running...")
    with redirect_stdout(log), redirect_stderr(log):
        long_running_work(progress_callback=log.progress_callback)
    log.flush()

Rich's Console resolves sys.stdout lazily, so redirect_stdout captures all
rprint output. Writes from worker threads are buffered and flushed on the
next main-thread write (Streamlit widget calls are main-thread only).
"""
import re
import threading
import time

import streamlit as st

_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\([0-9A-Z]|\x1b\][^\x07]*\x07')


class UILog:
    def __init__(self, placeholder=None, max_lines=300, min_interval=0.4, title=None):
        self.lines = []
        self.box = placeholder if placeholder is not None else st.empty()
        self.max_lines = max_lines
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()
        # Streamlit runs user scripts in a ScriptRunner thread, NOT the main
        # thread — so gate UI updates on the creating (script) thread, and
        # only buffer writes coming from worker threads (e.g. ThreadPoolExecutor).
        self._owner = threading.current_thread()
        if title:
            self.log(title)

    def _on_owner_thread(self):
        return threading.current_thread() is self._owner

    def _clean(self, s):
        # Collapse carriage-return redraws (rich progress bars) to last segment
        s = s.replace('\r', '\n')
        s = _ANSI_RE.sub('', s)
        return s

    def write(self, s):
        """File-like write so this object works with redirect_stdout."""
        if not s:
            return 0
        text = self._clean(s if isinstance(s, str) else str(s))
        new = [ln.rstrip() for ln in text.split('\n') if ln.strip()]
        if not new:
            return len(s)
        with self._lock:
            self.lines.extend(new)
            del self.lines[:-self.max_lines]
            if self._on_owner_thread():
                now = time.monotonic()
                if now - self._last >= self.min_interval:
                    self._last = now
                    self._render_locked()
        return len(s)

    def _render_locked(self):
        try:
            self.box.code('\n'.join(self.lines), language='text')
        except Exception:
            pass

    def flush(self):
        with self._lock:
            if self._on_owner_thread():
                self._last = 0.0
                self._render_locked()

    def log(self, msg):
        self.write(str(msg) + '\n')

    def progress_callback(self, step=None, detail=None, percent=None):
        """Compatible with core pipeline progress_callback(step, detail, percent)."""
        if detail:
            suffix = f'  [{percent:.0f}%]' if isinstance(percent, (int, float)) else ''
            self.log(f'{detail}{suffix}')
