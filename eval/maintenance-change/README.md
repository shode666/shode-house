# Experimental maintenance/change-task evaluation

This protocol measures whether a worker can explain an existing invariant and make
one small requirement change without avoidable rework or regression. It is an
opt-in experiment, not a release gate and not part of `eval/run-core.sh`.

## Campaign configuration

The reusable contract does not prescribe a model, revision or run count. This
release's exact model, arms, N, revisions, prompt/fixture/scorer hashes, limits,
required host capabilities, cost ceiling and cost authority are independently pinned
in `preregistration-4.2.0.json`; read that manifest for this campaign's values.
- Give both arms the same repository fixture, task prompt, host, model family,
  tool permissions, time limit and reviewer instructions.
- Run each worker in a clean worktree/session. A worker must first state the
  invariant it found, then implement the one recorded requirement delta and run
  the fixture's existing tests plus the smallest relevant regression test.
- Pin the candidate and baseline revisions, fixture hash, task prompt, host/CLI
  version, model identifier and scorer hash before the first run. Do not change a
  fixture, threshold or reviewer instruction after seeing results; a necessary
  correction starts a newly named experiment.

Claude-hosted and Codex-hosted runs are separate qualifications. Never pool them or
claim one host/model qualifies the other. Before a paid run, record that the host
can create fresh workers, select the requested model, preserve transcripts and
isolate worktrees, and record cost authority. A missing capability blocks only that
arm; static or unit tests do not substitute for behavioral evidence.

The current adapter accepts only bundle manifests with
`schema: claude-code-on-disk-v1`: a main JSONL plus paired subagent meta/JSONL files,
all hash-pinned in one run directory. The accepted captured layout is pinned to
Claude Code `2.1.286`. Codex and unknown schemas are
`BLOCKED: unverified-spawn-schema` / `UNSCORABLE`; Claude evidence never qualifies
Codex.

The complete consumed-field allowlist, exact JSON types, cardinalities and
contradiction policy are pinned in `schema-contract.md`. This is a strict adapter for
that captured host shape, not a general provenance validator or producer-authentication
mechanism; unsupported shapes fail closed.

## Task and evidence

Use one small, framework-neutral maintenance task whose repository fixture contains:

1. a discoverable invariant enforced by code and an existing test;
2. a requirement delta that changes one observable behavior without changing the
   invariant;
3. an intentionally tempting but incorrect shortcut that the existing tests expose;
4. deterministic validation commands with no network or external side effect.

For every run record the arm and exact revision, model requested and served, elapsed
time, changed paths, validation outcome, held-back regression outcome, number of
corrective edits after the first test run, final diff, transcript path and the
six-line reviewer verdict.
Time is descriptive only; no universal speed target or token-reduction target is a
pass criterion.

## Independent reviewer verdict

A fresh reviewer that did not author the change reads the completed pinned task
trace, diff and test output. The router cannot supply or complete the verdict. The
reviewer emits exactly these six non-empty closed-form lines:

```text
INVARIANT_EXPLANATION: MET|VIOLATED
CHANGE_FIDELITY: MET|VIOLATED
REGRESSION_SAFETY: MET|VIOLATED
TEST_EVIDENCE: MET|VIOLATED
REWORK_DISCIPLINE: MET|VIOLATED
OVERALL: PASS|FAIL
```

The final reviewer assistant text must contain only this contract. The scorer
normalizes CRLF/CR to LF and permits one terminal newline; prefixes, suffixes, extra
lines and extra blank lines are `UNSCORABLE`. Across every reviewer assistant text
event, exactly one whole-event contract may appear, and that event must be the final
assistant text with exactly one text block; zero/multiple verdict events, additional
text blocks, or non-string declared text values are `UNSCORABLE`.

Run the deterministic, network-free fixture/preflight with
`python3 eval/maintenance-change/runner.py --preflight`; it makes zero model calls
and reports `BLOCKED` while cost authority is false. Score a JSON array of run records
against the independent oracle with `python3 eval/maintenance-change/score.py
<preregistration> <records.json> <evidence-root>`. Missing, duplicate,
reordered, unknown, router-authored or conflicting replies, incomplete traces, wrong
models and wrong run counts are `UNSCORABLE`, never PASS. A complete verdict with
any `VIOLATED` dimension and consistent `OVERALL: FAIL` is a scored FAIL.

The scorer resolves each Claude Code evidence bundle inside the supplied evidence
root, validates the manifest's lowercase SHA-256 over main JSONL and paired subagent
meta/JSONL plus `raw/snap.jsonl` attribution bytes, then derives session, spawn
linkage, requested/served models, full execution windows, explicit successful tool
results and the fresh reviewer verdict with `trace_adapter.py`. The sole top-level
init must precede the sole top-level result, which must be the final raw run event.
For this captured campaign, top-level init/result events omit `parent_tool_use_id`;
an explicitly present parent field of any JSON type, including null, is rejected.
Main Agent/Task spawn blocks are authoritative only in `type: assistant` events and
linked tool-result completions only in `type: user` events; wrong-role blocks fail
closed.
Run, manifest, main-transcript, subagent and terminal-result session ids must all be
non-empty JSON strings. Subagent `spawnDepth` must be exact JSON integer `1` (not a
boolean or float). A linked tool result may omit `is_error` in the captured success
shape; when present it must be exact JSON boolean `false`.
Every subagent row timestamp, including empty-content assistant and user/tool rows,
must be strictly increasing and unique.
Reviewer Edit/Write/MultiEdit/NotebookEdit calls or a linked Bash snapshot change produce scored FAIL;
missing/ambiguous attribution is `UNSCORABLE`. Meta summary booleans are not trusted.
Snapshot attribution uses the repository hook's captured shape
`{ts,event,tool,tool_use_id,agent_id,subagent_type,head,files}`. Bash state is compared
only between the exact same-call PreToolUse/PostToolUse pair keyed by actor, tool id
and tool name, never against an adjacent global snapshot. A harmless Bash call with
a matching no-diff pair is not an edit; missing or mismatched linkage is `UNSCORABLE`.
Successful Claude tool completion is
the linked `tool_result` presence; an explicit host error is rejected, while the
captured success shape need not invent `is_error: false`.
The preregistration pins the actual hook surface
`Task|Agent|Bash|Edit|Write|MultiEdit|NotebookEdit`, the direct-edit subset, and the
proven read-only reviewer tools. Every reviewer snapshot and hooked transcript call
must reconcile bidirectionally by tool id/name; orphan, mismatch or duplicate evidence
is `UNSCORABLE`. Every snapshot that references a reviewer call id must carry the
reviewer actor and that call's exact tool; foreign or missing actors fail closed,
while unrelated implementer tool ids remain valid. Any other reviewer tool is also `UNSCORABLE` until that allowlist
changes in a newly preregistered campaign. Implementer edit snapshots remain valid;
the no-edit constraint applies to the independent reviewer.
Subagent identity is derived only from an exact safe
`agent-<id>.jsonl` transcript basename paired with exact
`agent-<same-id>.meta.json`; arbitrary, unsafe or mismatched basenames are rejected
before their contents become identity evidence. Hook cardinality is also exact:
reviewer Agent/Task/Bash calls require one ordered PreToolUse and one PostToolUse with
matching actor/type, while direct-edit tools require one PostToolUse. A reviewer
Agent/Task/Bash source-state delta is a demonstrated reviewer edit. The pinned
capture contract and `bash_same_call_pre_post` capability must be verified before a
live campaign can leave BLOCKED state.

Preflight verifies the pinned scenario/reviewer/capability-evidence hashes, host/CLI/
tool-permission identity, limits, exact candidate revision and positive authorized
cost ceiling. Capability names cannot be asserted on the command line. The current
campaign deliberately remains `BLOCKED`: its candidate revision cannot be pinned
without commit authority, host evidence is unverified and cost is unauthorized.

The report publishes raw results for every preregistered run before the arm summary. It
reports PASS/FAIL/UNSCORABLE counts per arm, quality dimensions, regression outcome,
elapsed time and rework. Elapsed time must be finite, numeric, non-boolean and
nonnegative. A recorded validation or held-back regression `FAIL` always produces a
scored FAIL; an all-MET/PASS reviewer verdict in that case is retained as an explicit
contradiction reason rather than allowing PASS. `UNSCORABLE` runs stay outside the pass-rate denominator,
remain disclosed, and leave qualification incomplete until rerun in a new directory
under the preregistered policy. Do not define a release threshold after seeing the
results; this first protocol produces evidence for this scenario/host/model only,
not general productivity and not a mandatory gate for every task.
