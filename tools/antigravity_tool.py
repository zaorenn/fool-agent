"""Google Antigravity integration tool for The Fool Agent.

Enables The Fool Agent to delegate complex tasks, code analysis, deep research,
and subagent operations to Google Antigravity (flash_lite, flash, pro) running
locally or via Google Generative Language API.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

ANTIGRAVITY_SCHEMA = {
    "name": "antigravity",
    "description": (
        "Interact with Google Antigravity autonomous agent system. "
        "Delegate complex tasks, coding requests, deep research, and second opinions "
        "to Antigravity models (flash_lite, flash, pro) running locally or via Google AI.\n\n"
        "Actions:\n"
        "- run: Start a new conversation with a prompt, wait for Antigravity's response, and return the result.\n"
        "- send: Send a follow-up message to an existing conversation.\n"
        "- metadata: Check status and metadata of an Antigravity conversation.\n"
        "- list: List recent Antigravity conversations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["run", "send", "metadata", "list"],
                "description": "Action to perform.",
            },
            "prompt": {
                "type": "string",
                "description": "The prompt or instruction for Antigravity (required for 'run' and 'send').",
            },
            "conversation_id": {
                "type": "string",
                "description": "The target conversation ID (required for 'send' and 'metadata').",
            },
            "model": {
                "type": "string",
                "enum": ["flash_lite", "flash", "pro"],
                "description": "Model tier: 'flash' (fast/capable), 'pro' (deep reasoning/coding), 'flash_lite' (lightweight). Defaults to 'flash'.",
            },
            "title": {
                "type": "string",
                "description": "Optional title for the new conversation.",
            },
            "profile": {
                "type": "string",
                "description": "Optional profile name for Antigravity.",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds to wait for Antigravity response (default 120, max 600).",
            },
        },
        "required": ["action"],
    },
}


def _resolve_agentapi_cmd() -> Optional[str]:
    """Find the agentapi executable or bat file."""
    cmd = shutil.which("agentapi")
    if cmd:
        return cmd
    if sys.platform == "win32":
        cmd = shutil.which("agentapi.bat")
        if cmd:
            return cmd
        # Well-known path on Windows
        candidate = Path.home() / ".gemini" / "antigravity" / "bin" / "agentapi.bat"
        if candidate.exists():
            return str(candidate)
    else:
        candidate = Path.home() / ".gemini" / "antigravity" / "bin" / "agentapi"
        if candidate.exists():
            return str(candidate)
    return None


def check_antigravity_requirements() -> bool:
    """Check if Antigravity tools can be used."""
    if _resolve_agentapi_cmd() is not None:
        return True
    # Check if Google / Gemini / Antigravity credentials are configured
    if any(os.environ.get(k) for k in ("ANTIGRAVITY_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")):
        return True
    try:
        from agent.secret_scope import get_secret
        if any(get_secret(k) for k in ("ANTIGRAVITY_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")):
            return True
    except Exception:
        pass
    return False


def _get_transcript_path(conversation_id: str) -> Path:
    """Get the transcript.jsonl path for an Antigravity conversation."""
    return (
        Path.home()
        / ".gemini"
        / "antigravity"
        / "brain"
        / conversation_id
        / ".system_generated"
        / "logs"
        / "transcript.jsonl"
    )


def _poll_conversation_response(
    conversation_id: str,
    start_step_count: int = 0,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Poll transcript.jsonl until a completed response is produced."""
    log_file = _get_transcript_path(conversation_id)
    deadline = time.time() + max(5, min(timeout_seconds, 600))
    last_content = None
    step_count = 0

    while time.time() < deadline:
        if log_file.exists():
            try:
                text = log_file.read_text(encoding="utf-8", errors="ignore")
                lines = [json.loads(l) for l in text.splitlines() if l.strip()]
                step_count = len(lines)
                for item in reversed(lines):
                    s_idx = item.get("step_index", 0)
                    if s_idx < start_step_count:
                        break
                    if item.get("type") == "PLANNER_RESPONSE":
                        status = item.get("status")
                        content = item.get("content")
                        if content and content != "None":
                            last_content = content
                        if status == "DONE" and last_content:
                            return {
                                "success": True,
                                "conversation_id": conversation_id,
                                "response": last_content,
                                "steps_executed": step_count - start_step_count,
                            }
            except Exception as exc:
                logger.debug("Error reading transcript for %s: %s", conversation_id, exc)

        time.sleep(0.5)

    if last_content:
        return {
            "success": True,
            "conversation_id": conversation_id,
            "response": last_content,
            "partial": True,
            "warning": "Response returned before turn finished cleanly or timed out.",
        }

    return {
        "success": False,
        "conversation_id": conversation_id,
        "error": f"Antigravity did not return a response within {timeout_seconds}s.",
    }


def handle_antigravity(args: Dict[str, Any], **kw: Any) -> str:
    """Main handler for the antigravity tool."""
    action = str(args.get("action", "")).strip().lower()
    prompt = str(args.get("prompt", "")).strip()
    cid = str(args.get("conversation_id", "")).strip()
    model = str(args.get("model", "flash")).strip().lower()
    if model not in ("flash_lite", "flash", "pro"):
        model = "flash"
    title = str(args.get("title", "")).strip()
    profile = str(args.get("profile", "")).strip()
    timeout = int(args.get("timeout", 120) or 120)

    agentapi_cmd = _resolve_agentapi_cmd()
    if not agentapi_cmd:
        return json.dumps(
            {
                "success": False,
                "error": "Antigravity CLI (agentapi) not found on system. Install Antigravity or ensure agentapi is on PATH.",
            },
            ensure_ascii=False,
        )

    # 1. Action: run
    if action == "run":
        if not prompt:
            return json.dumps({"success": False, "error": "'prompt' is required for action='run'."})

        cmd = [agentapi_cmd, "new-conversation", f"--model={model}"]
        if title:
            cmd.append(f"--title={title}")
        if profile:
            cmd.append(f"--profile={profile}")
        cmd.append(prompt)

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            if res.returncode != 0:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"agentapi new-conversation failed: {res.stderr or res.stdout}",
                    },
                    ensure_ascii=False,
                )

            data = json.loads(res.stdout)
            conv_id = data.get("response", {}).get("newConversation", {}).get("conversationId")
            if not conv_id:
                return json.dumps(
                    {
                        "success": False,
                        "raw_output": res.stdout,
                        "error": "Could not parse conversationId from Antigravity output.",
                    },
                    ensure_ascii=False,
                )

            result = _poll_conversation_response(conv_id, start_step_count=0, timeout_seconds=timeout)
            result["model"] = model
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"success": False, "error": f"Failed to execute Antigravity: {exc}"})

    # 2. Action: send
    elif action == "send":
        if not cid:
            return json.dumps({"success": False, "error": "'conversation_id' is required for action='send'."})
        if not prompt:
            return json.dumps({"success": False, "error": "'prompt' is required for action='send'."})

        log_file = _get_transcript_path(cid)
        start_count = 0
        if log_file.exists():
            try:
                start_count = len([l for l in log_file.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()])
            except Exception:
                pass

        cmd = [agentapi_cmd, "send-message", cid, prompt]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            if res.returncode != 0:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"agentapi send-message failed: {res.stderr or res.stdout}",
                    },
                    ensure_ascii=False,
                )

            result = _poll_conversation_response(cid, start_step_count=start_count, timeout_seconds=timeout)
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"success": False, "error": f"Failed to send message to Antigravity: {exc}"})

    # 3. Action: metadata
    elif action == "metadata":
        if not cid:
            return json.dumps({"success": False, "error": "'conversation_id' is required for action='metadata'."})

        cmd = [agentapi_cmd, "get-conversation-metadata", cid]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20,
                encoding="utf-8",
                errors="replace",
            )
            if res.returncode != 0:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"agentapi get-conversation-metadata failed: {res.stderr or res.stdout}",
                    },
                    ensure_ascii=False,
                )
            try:
                data = json.loads(res.stdout)
                return json.dumps({"success": True, "metadata": data.get("response", {}).get("conversationMetadata", {})}, ensure_ascii=False)
            except Exception:
                return json.dumps({"success": True, "raw": res.stdout}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"success": False, "error": f"Failed to get metadata: {exc}"})

    # 4. Action: list
    elif action == "list":
        conv_dir = Path.home() / ".gemini" / "antigravity" / "conversations"
        results = []
        if conv_dir.exists():
            for db_file in sorted(conv_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]:
                cid_name = db_file.stem
                results.append({
                    "conversation_id": cid_name,
                    "updated_at": db_file.stat().st_mtime,
                })
        return json.dumps({"success": True, "conversations": results}, ensure_ascii=False)

    else:
        return json.dumps(
            {
                "success": False,
                "error": f"Unknown action '{action}'. Supported actions: 'run', 'send', 'metadata', 'list'.",
            }
        )


registry.register(
    name="antigravity",
    toolset="antigravity",
    schema=ANTIGRAVITY_SCHEMA,
    handler=lambda args, **kw: handle_antigravity(args, **kw),
    check_fn=check_antigravity_requirements,
    emoji="🪐",
)
