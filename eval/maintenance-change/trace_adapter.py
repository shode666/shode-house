"""Fail-closed Claude Code on-disk bundle adapter for maintenance evaluation."""

import datetime as dt
import hashlib
import json
import math
import pathlib
import re

HEX = re.compile(r"^[0-9a-f]{64}$")
AGENT_FILE = re.compile(r"^agent-([A-Za-z0-9][A-Za-z0-9_-]*)\.jsonl$")
META_FILE = re.compile(r"^agent-([A-Za-z0-9][A-Za-z0-9_-]*)\.meta\.json$")
VERDICT_CONTRACT = re.compile(r"INVARIANT_EXPLANATION: (?:MET|VIOLATED)\nCHANGE_FIDELITY: (?:MET|VIOLATED)\nREGRESSION_SAFETY: (?:MET|VIOLATED)\nTEST_EVIDENCE: (?:MET|VIOLATED)\nREWORK_DISCIPLINE: (?:MET|VIOLATED)\nOVERALL: (?:PASS|FAIL)")


class EvidenceError(ValueError): pass


def _objects(path, jsonl=True):
    try:
        raw = path.read_text(encoding="utf-8")
        values = [json.loads(line) for line in raw.splitlines() if line.strip()] if jsonl else [json.loads(raw)]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc: raise EvidenceError(f"malformed evidence: {path.name}: {exc}")
    if not values or any(not isinstance(value, dict) for value in values): raise EvidenceError(f"non-object evidence: {path.name}")
    return values


def _time(value):
    try: return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError): raise EvidenceError("missing or invalid timestamp")


def _safe(root, rel):
    if not isinstance(rel, str): raise EvidenceError("manifest path missing")
    path = (root / rel).resolve()
    if root not in path.parents or not path.is_file(): raise EvidenceError("manifest path escapes or is missing")
    return path


def _normalized_verdict(value):
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized[:-1] if normalized.endswith("\n") else normalized


def _session(value):
    return type(value) is str and bool(value)


def _top_level(event):
    return "parent_tool_use_id" not in event


def _message(event):
    message = event.get("message")
    if not isinstance(message, dict): raise EvidenceError("message must be an object")
    content = message.get("content")
    if not isinstance(content, list) or any(not isinstance(block, dict) for block in content): raise EvidenceError("content must be an object list")
    return message, content


def extract_bundle(bundle_path, evidence_root, preregistration):
    evidence_root = pathlib.Path(evidence_root).resolve(); bundle = (evidence_root / bundle_path).resolve()
    if evidence_root not in bundle.parents or not bundle.is_dir(): raise EvidenceError("bundle outside evidence root")
    manifest_path = bundle / "manifest.json"; manifest = _objects(manifest_path, False)[0]
    if manifest.get("schema") != "claude-code-on-disk-v1": raise EvidenceError("unsupported host schema")
    if not isinstance(manifest.get("run_id"), str) or not manifest.get("run_id"): raise EvidenceError("manifest run id missing")
    semantics = manifest.get("protocol_hashes")
    semantic_keys = ("trace_adapter_sha256", "runner_sha256", "scorer_sha256", "scenario_sha256", "reviewer_contract_sha256", "hook_snap_sha256", "capture_contract_sha256", "schema_contract_sha256")
    if not isinstance(semantics, dict) or any(semantics.get(key) != preregistration.get(key) for key in semantic_keys): raise EvidenceError("protocol semantic hash mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files: raise EvidenceError("manifest files missing")
    resolved = {}
    for rel, expected in files.items():
        if not isinstance(expected, str) or not HEX.fullmatch(expected): raise EvidenceError("nonhex manifest hash")
        path = _safe(bundle, rel)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected: raise EvidenceError("bundle hash mismatch")
        resolved[rel] = path
    main_rel = manifest.get("main"); run_rel = manifest.get("run")
    pairs = manifest.get("subagents"); snap_rel = manifest.get("snapshot")
    if main_rel not in resolved or run_rel not in resolved or snap_rel not in resolved or not isinstance(pairs, list) or len(pairs) != 2: raise EvidenceError("bundle inventory incomplete")
    declared = {main_rel, run_rel, snap_rel}
    for pair in pairs:
        if not isinstance(pair, dict) or pair.get("jsonl") not in resolved or pair.get("meta") not in resolved: raise EvidenceError("subagent pair missing")
        declared.update((pair["jsonl"], pair["meta"]))
    if declared != set(resolved): raise EvidenceError("extra or duplicate manifest files")

    run = _objects(resolved[run_rel]); main = _objects(resolved[main_rel]); snapshots = _objects(resolved[snap_rel])
    markers = [e for e in run if e.get("type") == "result" or e.get("type") == "system" and e.get("subtype") == "init"]
    if any(not _top_level(e) for e in markers): raise EvidenceError("init/result parent shape invalid")
    init = [e for e in markers if e.get("type") == "system"]
    results = [e for e in markers if e.get("type") == "result"]
    if len(init) != 1 or len(results) != 1: raise EvidenceError("missing or conflicting init/result")
    if run.index(init[0]) >= run.index(results[0]): raise EvidenceError("terminal result precedes run init")
    if run.index(results[0]) != len(run) - 1: raise EvidenceError("terminal result is not final run event")
    session = init[0].get("session_id"); main_model = init[0].get("model")
    if (not _session(session) or not main_model or init[0].get("claude_code_version") != manifest.get("cli_version")
            or manifest.get("cli_version") not in preregistration.get("claude_cli_versions", [])): raise EvidenceError("init provenance mismatch")
    result = results[0]
    if not _session(result.get("session_id")) or result.get("session_id") != session or result.get("subtype") != "success" or result.get("is_error") is not False: raise EvidenceError("run did not complete successfully")
    if not _session(manifest.get("session_id")) or manifest.get("session_id") != session: raise EvidenceError("manifest session mismatch")
    if any(not _session(e.get("sessionId")) or e.get("sessionId") != session for e in main): raise EvidenceError("mixed main session")

    spawns, completions = {}, {}
    main_times = []
    for event in main:
        stamp = _time(event.get("timestamp"))
        if not isinstance(event.get("message"), dict):
            if event.get("type") in ("assistant", "user"): raise EvidenceError("message must be an object")
            continue
        main_times.append(stamp)
        _, content = _message(event)
        for block in content:
            if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                if event.get("type") != "assistant": raise EvidenceError("spawn block has wrong event role")
                tool_id = block.get("id"); inp = block.get("input")
                if not tool_id or tool_id in spawns or not isinstance(inp, dict): raise EvidenceError("duplicate or malformed spawn")
                spawns[tool_id] = (inp, stamp)
            if block.get("type") == "tool_result":
                if event.get("type") != "user": raise EvidenceError("completion block has wrong event role")
                tool_id = block.get("tool_use_id")
                if not tool_id or tool_id in completions: raise EvidenceError("duplicate or failed completion")
                if "is_error" in block and (type(block["is_error"]) is not bool or block["is_error"] is not False): raise EvidenceError("completion error field invalid")
                completions[tool_id] = stamp
    if main_times != sorted(main_times) or len(set(main_times)) != len(main_times): raise EvidenceError("main timestamps are non-monotonic or ambiguous")

    role_spawns = {name: [] for name in preregistration.get("roles", {})}
    for tool_id, (inp, _) in spawns.items():
        for name, config in preregistration.get("roles", {}).items():
            prompt = inp.get("prompt")
            if inp.get("subagent_type") == config.get("subagent_type") and isinstance(prompt, str) and config.get("delegation_marker") in prompt: role_spawns[name].append(tool_id)
    if any(len(ids) != 1 for ids in role_spawns.values()): raise EvidenceError("matching role spawn count is not exactly one")

    roles = {}
    for pair in pairs:
        match = AGENT_FILE.fullmatch(pathlib.Path(pair["jsonl"]).name)
        if not match: raise EvidenceError("subagent transcript filename invalid")
        agent_id = match.group(1)
        meta_match = META_FILE.fullmatch(pathlib.Path(pair["meta"]).name)
        if not meta_match or meta_match.group(1) != agent_id: raise EvidenceError("paired meta filename invalid")
        meta = _objects(resolved[pair["meta"]], False)[0]; rows = _objects(resolved[pair["jsonl"]])
        if any(not isinstance(meta.get(key), kind) for key, kind in (("toolUseId", str),("agentType", str))): raise EvidenceError("meta field type invalid")
        if type(meta.get("spawnDepth")) is not int or meta["spawnDepth"] != 1: raise EvidenceError("spawn depth invalid")
        tool_id = meta.get("toolUseId"); spawn = spawns.get(tool_id)
        if not spawn or tool_id not in completions: raise EvidenceError("unresolved spawn/completion")
        inp, spawn_t = spawn
        if not agent_id or meta.get("agentType") != inp.get("subagent_type"): raise EvidenceError("spawn/meta identity mismatch")
        if any(r.get("agentId") != agent_id or not _session(r.get("sessionId")) or r.get("sessionId") != session or r.get("isSidechain") is not True for r in rows): raise EvidenceError("subagent identity/session mismatch")
        role = None
        for name, config in preregistration.get("roles", {}).items():
            if inp.get("subagent_type") == config.get("subagent_type") and config.get("delegation_marker") in inp.get("prompt", ""): role = name
        if not role or role in roles: raise EvidenceError("role linkage ambiguous")
        if inp.get("model") != preregistration.get("exact_model"): raise EvidenceError("requested model missing or wrong")
        messages = []
        for row in rows:
            if not isinstance(row.get("message"), dict):
                if row.get("type") in ("assistant", "user"): raise EvidenceError("message must be an object")
                continue
            message, content = _message(row); messages.append((row, message, content, _time(row.get("timestamp"))))
            if row.get("type") == "assistant" and not isinstance(message.get("usage"), dict): raise EvidenceError("assistant usage must be an object")
            if any(block.get("type") == "text" and type(block.get("text")) is not str for block in content): raise EvidenceError("text block value must be a string")
            if any(block.get("type") == "tool_use" for block in content) and row.get("type") != "assistant": raise EvidenceError("subagent tool call has wrong event role")
            if any(block.get("type") == "tool_result" for block in content) and row.get("type") != "user": raise EvidenceError("subagent tool result has wrong event role")
        models = {m.get("model") for r,m,_,_ in messages if r.get("type") == "assistant" and m.get("model") != "<synthetic>"}
        if models != {preregistration.get("exact_model")}: raise EvidenceError("served model missing, wrong, or mixed")
        times = [_time(r.get("timestamp")) for r in rows]
        if times != sorted(times) or len(set(times)) != len(times): raise EvidenceError("subagent timestamps are non-monotonic or ambiguous")
        text_events, verdict_events = [], []
        for row, _, content, stamp in messages:
            if row.get("type") != "assistant": continue
            texts = [block["text"] for block in content if block.get("type") == "text" and isinstance(block.get("text"), str)]
            text_events.extend((stamp, text) for text in texts)
            matches = [normalized for text in texts for normalized in (_normalized_verdict(text),) if VERDICT_CONTRACT.fullmatch(normalized)]
            if matches and (len(texts) != 1 or len(matches) != 1): raise EvidenceError("reviewer verdict event text cardinality invalid")
            verdict_events.extend((stamp, match) for match in matches)
        if text_events and sum(t == max(x[0] for x in text_events) for t,_ in text_events) != 1: raise EvidenceError("final assistant timestamp is ambiguous")
        tool_calls = [b for _,_,content,_ in messages for b in content if b.get("type") == "tool_use"]
        roles[role] = {"agent_id":agent_id,"tool_id":tool_id,"spawn":spawn_t,"start":min(times),"end":max(times),"complete":completions[tool_id],"final_stamp":max(text_events)[0] if text_events else None,"verdict_events":verdict_events,"tool_calls":tool_calls}
    if set(roles) != {"implementer", "reviewer"}: raise EvidenceError("required roles missing")
    imp, rev = roles["implementer"], roles["reviewer"]
    if imp["agent_id"] == rev["agent_id"] or imp["tool_id"] == rev["tool_id"]: raise EvidenceError("actors are not distinct")
    if not (imp["spawn"] <= imp["start"] <= imp["end"] <= imp["complete"] < rev["spawn"] <= rev["start"] <= rev["end"] <= rev["complete"]): raise EvidenceError("execution order invalid")
    policy = preregistration.get("reviewer_edit_policy", {})
    edit_tools = set(policy.get("edit_tools", [])); read_only_tools = set(policy.get("read_only_tools", [])); snapshot_tools = set(policy.get("snapshot_tools", []))
    pre_post_tools = set(policy.get("pre_post_tools", [])); post_only_tools = set(policy.get("post_only_tools", []))
    if (edit_tools != {"Edit", "Write", "MultiEdit", "NotebookEdit"} or not read_only_tools
            or pre_post_tools != {"Task", "Agent", "Bash"} or post_only_tools != edit_tools
            or snapshot_tools != pre_post_tools | post_only_tools):
        raise EvidenceError("reviewer tool policy missing or malformed")
    reviewer_tool_edit = False
    if not snapshots: raise EvidenceError("snapshot attribution missing or malformed")
    snap_keys, snap_times = set(), []
    for sn in snapshots:
        stamp = sn.get("ts"); event = sn.get("event"); tool = sn.get("tool"); tool_id = sn.get("tool_use_id")
        actor = sn.get("agent_id"); subtype = sn.get("subagent_type"); head = sn.get("head"); files_state = sn.get("files")
        if (not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not math.isfinite(stamp) or stamp <= 0
                or event not in {"PreToolUse", "PostToolUse"} or tool not in snapshot_tools
                or not isinstance(tool_id, str) or not tool_id
                or actor is not None and (not isinstance(actor, str) or not actor)
                or subtype is not None and (not isinstance(subtype, str) or not subtype)
                or not isinstance(head, str) or not head
                or not isinstance(files_state, dict)
                or any(not isinstance(path, str) or not path or not isinstance(digest, str) or not digest for path, digest in files_state.items())):
            raise EvidenceError("snapshot attribution missing or malformed")
        key = (actor, tool_id, event)
        if key in snap_keys or stamp in snap_times: raise EvidenceError("snapshot attribution is duplicate or ambiguous")
        snap_keys.add(key); snap_times.append(stamp)
    if snap_times != sorted(snap_times): raise EvidenceError("snapshot timestamps are non-monotonic")
    reviewer_snapshots = [(index, sn) for index, sn in enumerate(snapshots) if sn["agent_id"] == rev["agent_id"]]
    calls_by_id = {}
    for call in rev["tool_calls"]:
        name, inp, call_id = call.get("name"), call.get("input"), call.get("id")
        if not isinstance(name, str) or not name or not isinstance(call_id, str) or not call_id or not isinstance(inp, dict): raise EvidenceError("tool input must be an object")
        if call_id in calls_by_id: raise EvidenceError("duplicate reviewer tool call")
        calls_by_id[call_id] = call
        call_snapshots = [(index, sn) for index, sn in enumerate(snapshots) if sn["tool_use_id"] == call_id]
        if any(sn["agent_id"] != rev["agent_id"] or sn["tool"] != name for _, sn in call_snapshots): raise EvidenceError("reviewer call snapshot actor or tool mismatch")
        matches = call_snapshots
        if name in snapshot_tools:
            required_events = {"PreToolUse", "PostToolUse"} if name in pre_post_tools else {"PostToolUse"}
            if len(matches) != len(required_events) or {sn["event"] for _, sn in matches} != required_events: raise EvidenceError("reviewer tool attribution missing or mismatched")
            by_event = {sn["event"]: (index, sn) for index, sn in matches}
            index, current = by_event["PostToolUse"]
            if name in pre_post_tools:
                pre_index, prior = by_event["PreToolUse"]
                expected_type = inp.get("subagent_type") if name in {"Agent", "Task"} else None
                if (pre_index >= index or name in {"Agent", "Task"} and (not isinstance(expected_type, str) or not expected_type)
                        or prior["subagent_type"] != expected_type or current["subagent_type"] != expected_type):
                    raise EvidenceError("reviewer spawn attribution invalid")
                prior = by_event["PreToolUse"][1]
                changed = any(current["files"].get(path) != prior["files"].get(path) for path in set(current["files"]) | set(prior["files"]))
                if changed or current["head"] != prior["head"]: reviewer_tool_edit = True
            elif current["subagent_type"] is not None:
                raise EvidenceError("reviewer tool attribution invalid")
            elif name in edit_tools: reviewer_tool_edit = True
        elif name not in read_only_tools:
            raise EvidenceError("unknown reviewer tool cannot be proven read-only")
    for _, snapshot in reviewer_snapshots:
        call = calls_by_id.get(snapshot["tool_use_id"])
        allowed_events = {"PreToolUse", "PostToolUse"} if snapshot["tool"] in pre_post_tools else {"PostToolUse"}
        if not call or call.get("name") != snapshot["tool"] or snapshot["event"] not in allowed_events:
            raise EvidenceError("orphan or mismatched reviewer snapshot")
    if len(rev["verdict_events"]) != 1: raise EvidenceError("reviewer verdict event count is not exactly one")
    verdict_stamp, verdict_text = rev["verdict_events"][-1]
    if verdict_stamp != rev["final_stamp"]: raise EvidenceError("reviewer verdict is not the final assistant text")
    return {"host":"claude","run_id":manifest["run_id"],"session_id":session,"main_model":main_model,"requested_models":{"implementer":preregistration["exact_model"],"reviewer":preregistration["exact_model"]},"served_models":{"implementer":preregistration["exact_model"],"reviewer":preregistration["exact_model"]},"verdict":verdict_text,"reviewer_edit":reviewer_tool_edit}
