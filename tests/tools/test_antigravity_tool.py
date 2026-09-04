"""Unit tests for Google Antigravity tool and authentication integration."""

import json
from unittest.mock import MagicMock, patch

import pytest

from fool_cli.auth import get_antigravity_auth_status, resolve_antigravity_runtime_credentials
from tools.antigravity_tool import (
    ANTIGRAVITY_SCHEMA,
    check_antigravity_requirements,
    handle_antigravity,
)
from tools.registry import registry


def test_antigravity_tool_is_registered():
    tool = registry.get_entry("antigravity")
    assert tool is not None
    assert tool.toolset == "antigravity"
    assert tool.schema["name"] == "antigravity"
    assert tool.emoji == "🪐"


def test_antigravity_schema_structure():
    assert ANTIGRAVITY_SCHEMA["name"] == "antigravity"
    params = ANTIGRAVITY_SCHEMA["parameters"]["properties"]
    assert "action" in params
    assert "prompt" in params
    assert "conversation_id" in params
    assert "model" in params
    assert params["action"]["enum"] == ["run", "send", "metadata", "list"]


def test_check_antigravity_requirements(monkeypatch):
    monkeypatch.setattr("tools.antigravity_tool._resolve_agentapi_cmd", lambda: "/path/to/agentapi")
    assert check_antigravity_requirements() is True

    monkeypatch.setattr("tools.antigravity_tool._resolve_agentapi_cmd", lambda: None)
    monkeypatch.delenv("ANTIGRAVITY_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert check_antigravity_requirements() is False

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert check_antigravity_requirements() is True


def test_handle_antigravity_unknown_action(monkeypatch):
    monkeypatch.setattr("tools.antigravity_tool._resolve_agentapi_cmd", lambda: "/bin/agentapi")
    res_str = handle_antigravity({"action": "invalid_action"})
    res = json.loads(res_str)
    assert res["success"] is False
    assert "Unknown action" in res["error"]


def test_handle_antigravity_run_missing_prompt(monkeypatch):
    monkeypatch.setattr("tools.antigravity_tool._resolve_agentapi_cmd", lambda: "/bin/agentapi")
    res_str = handle_antigravity({"action": "run"})
    res = json.loads(res_str)
    assert res["success"] is False
    assert "'prompt' is required" in res["error"]


def test_handle_antigravity_send_missing_cid(monkeypatch):
    monkeypatch.setattr("tools.antigravity_tool._resolve_agentapi_cmd", lambda: "/bin/agentapi")
    res_str = handle_antigravity({"action": "send", "prompt": "hi"})
    res = json.loads(res_str)
    assert res["success"] is False
    assert "'conversation_id' is required" in res["error"]


def test_handle_antigravity_metadata_success(monkeypatch):
    monkeypatch.setattr("tools.antigravity_tool._resolve_agentapi_cmd", lambda: "/bin/agentapi")
    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = json.dumps({"response": {"conversationMetadata": {"workspaces": []}}})
    with patch("subprocess.run", return_value=mock_run):
        res_str = handle_antigravity({"action": "metadata", "conversation_id": "test-cid"})
        res = json.loads(res_str)
        assert res["success"] is True
        assert "metadata" in res


def test_auth_status_resolution(monkeypatch):
    monkeypatch.setattr("fool_cli.auth._antigravity_cli_path", lambda: "/bin/agentapi")
    status = get_antigravity_auth_status()
    assert status["logged_in"] is True
    assert status["source"] == "local-antigravity"

    creds = resolve_antigravity_runtime_credentials()
    assert creds["provider"] == "antigravity"
    assert creds["api_key"] == "local-session"
