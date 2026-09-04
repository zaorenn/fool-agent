"""Tests for the interim_assistant_callback config gating in tui_gateway.

These tests exercise the real _agent_cbs() wiring rather than a local
imitation, so a break in the production callback registration is caught.
"""

from __future__ import annotations

from unittest.mock import patch


def test_load_interim_assistant_messages_defaults_true():
    from tui_gateway.server import _load_interim_assistant_messages

    with patch("tui_gateway.server._load_cfg", return_value={}):
        assert _load_interim_assistant_messages() is True


def test_agent_cbs_includes_interim_callback_when_enabled():
    """_agent_cbs() includes interim_assistant_callback when the config is on.

    Exercises the real _agent_cbs() wiring: the callback must be present in
    the returned dict and, when invoked, must emit a message.interim event
    with the text and already_streamed flag passed through.
    """
    from tui_gateway.server import _agent_cbs

    emitted: list[tuple] = []

    def fake_emit(event_type, sid, payload=None):
        emitted.append((event_type, sid, payload))

    with patch("tui_gateway.server._load_cfg", return_value={}), \
         patch("tui_gateway.server._emit", side_effect=fake_emit):
        cbs = _agent_cbs("test-session")

        assert "interim_assistant_callback" in cbs
        cb = cbs["interim_assistant_callback"]
        assert callable(cb)

        # Invoke the real callback inside the patch context — the lambda
        # resolves _emit by name at call time, so it must be called while
        # the patch is active.
        cb("hello world", already_streamed=True)

    assert len(emitted) == 1
    assert emitted[0][0] == "message.interim"
    assert emitted[0][1] == "test-session"
    assert emitted[0][2]["text"] == "hello world"
    assert emitted[0][2]["already_streamed"] is True


def test_run_prompt_submit_handles_none_agent_gracefully(monkeypatch):
    """When session['agent'] is None, _run_prompt_submit must not crash with
    AttributeError: 'NoneType' object has no attribute 'interim_assistant_callback'."""
    import threading
    import tui_gateway.server as server

    class _SyncThread:
        def __init__(self, target, daemon=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(server, "_RealThread", _SyncThread)

    emitted = []

    def fake_emit(event_type, sid, payload=None):
        emitted.append((event_type, sid, payload))

    monkeypatch.setattr(server, "_emit", fake_emit)

    session = {
        "agent": None,
        "session_key": "test-key",
        "history": [],
        "history_lock": threading.Lock(),
        "history_version": 0,
        "running": True,
        "attached_images": [],
        "cols": 80,
    }

    server._run_prompt_submit("rid", "sid", session, "hello")
    if session.get("_run_thread"):
        session["_run_thread"].join(timeout=5.0)
    terminal_events = [e for e in emitted if e[0] in ("message.complete", "error")]
    assert len(terminal_events) >= 1


