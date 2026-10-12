#!/usr/bin/env python3
"""Restore the Codex coordinator contract at session and worker boundaries."""
import json
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        print("shode-house: invalid lifecycle-hook input", file=sys.stderr)
        return 2
    event = payload.get("hook_event_name")
    if event not in {"SessionStart", "SubagentStart"}:
        print("shode-house: unexpected lifecycle-hook event", file=sys.stderr)
        return 2
    source = payload.get("source", "unknown")
    context = (
        "SHODE_CODEX_HOOKS=ACTIVE (hook-reported, not an authentication signal). "
        "Enter Shode House through shode-house:ask. "
        "Use genuine separate workers for delegated roles and fresh workers for independent review axes; "
        "do not role-play missing workers. Shell commands and host-level per-role model, tool, and scope "
        "isolation remain ADVISORY-ONLY; rely on Codex sandbox and approval controls."
    )
    if event == "SessionStart" and source == "compact":
        context += " Context was restored after compaction; reload the ask coordinator contract before continuing."
    if event == "SubagentStart":
        context += " This worker must read the supplied full role path and prerequisite skills before working."
    json.dump({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
