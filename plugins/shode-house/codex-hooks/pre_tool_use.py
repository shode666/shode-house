#!/usr/bin/env python3
"""Fail closed on direct writes to Shode House control-plane and Git paths."""
import json
import os
from pathlib import Path
import posixpath
import re
import sys
import unicodedata


PROTECTED = re.compile(
    r"(?:^|[^A-Za-z0-9_.-])(?:\.git|\.shode-house[/\\](?:state|journal|scope))(?:[/\\]|$)", re.I
)
PATCH_PATH = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$", re.M)


def deny(reason):
    print(f"DENY: {reason}", file=sys.stderr)
    return 2


def protected_path(value):
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        return True
    normalized = posixpath.normpath(value.replace("\\", "/")).casefold()
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if ".git" in parts:
        return True
    pairs = zip(parts, parts[1:])
    return any(left == ".shode-house" and right in {"state", "journal", "scope"}
               for left, right in pairs)


def resolved_protected_path(value, cwd):
    """Catch an ordinary-looking path whose existing ancestor is a symlink into a protected path."""
    candidate = Path(value.replace("\\", os.sep))
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return True
    return protected_path(resolved.as_posix())


def ambiguous_hardlink(value, cwd):
    """A write through a second name changes every hard-linked name; the protected peer is unknowable cheaply."""
    candidate = Path(value.replace("\\", os.sep))
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    try:
        return candidate.is_file() and candidate.stat().st_nlink > 1
    except OSError:
        return True


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return deny("invalid PreToolUse JSON")
    if payload.get("hook_event_name") != "PreToolUse":
        return deny("unexpected hook event")
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return deny("missing tool identity or input")
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return deny("missing working directory")

    candidates = []
    if tool == "apply_patch":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return deny("apply_patch command is missing")
        candidates.extend(PATCH_PATH.findall(command))
    elif tool in {"Edit", "Write"}:
        path = tool_input.get("file_path", tool_input.get("path"))
        if not isinstance(path, str):
            return deny(f"{tool} path is missing")
        candidates.append(path)
    else:
        return deny(f"unsupported guarded tool: {tool}")

    if any(PROTECTED.search(value) or protected_path(value) or resolved_protected_path(value, cwd)
           or ambiguous_hardlink(value, cwd)
           for value in candidates):
        return deny("direct mutation of protected, unresolved, or hard-linked paths is not allowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
