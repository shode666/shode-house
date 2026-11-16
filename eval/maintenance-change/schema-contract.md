# Claude Code 2.1.286 maintenance evidence contract

This is the complete allowlist for fields consumed by the experimental adapter. It
is not a general JSON validator. Unlisted host/schema versions are unsupported;
unconsumed extension fields are ignored only when they cannot affect the fields,
events, identities, order or verdicts below.

| Surface | Consumed field | Required / accepted shape | Semantic constraints |
|---|---|---|---|
| manifest | `schema` | required string | exact `claude-code-on-disk-v1` |
| manifest | `run_id` | required non-empty string | equals score record and unique in batch |
| manifest | `main`, `run`, `snapshot` | required relative path strings | declared, hashed, regular files inside bundle |
| manifest | `subagents` | required list of exactly 2 objects | each has declared `jsonl` and `meta`; inventory exact |
| manifest | `files` | required non-empty object | relative path keys; lowercase hex SHA-256 values; exact declared inventory |
| manifest | `protocol_hashes` | required object | every preregistered semantic hash equals oracle |
| manifest | `cli_version`, `session_id` | required strings | exact pinned CLI; non-empty session shared by all surfaces |
| run init | `type`, `subtype` | required strings | exact `system` / `init`; exactly one; `parent_tool_use_id` forbidden |
| run init | `session_id`, `model`, `claude_code_version` | required | non-empty session string; model string later equals oracle; exact CLI version |
| run result | `type`, `subtype`, `is_error`, `session_id` | required | exact `result`, `success`, boolean false, shared non-empty session; exactly one and final row; parent field forbidden |
| main row | `type`, `sessionId`, `timestamp`, `message.content` | required when consumed | assistant spawn / user completion roles; shared session; ISO timestamp strictly ordered/unique; content list of objects |
| main spawn | `type`, `name`, `id`, `input` | required | exact `tool_use`, Agent/Task, non-empty unique id, object input; role subagent type/marker exactly once; requested model exact |
| main completion | `type`, `tool_use_id`, `is_error` | id required; error optional | exact `tool_result`; unique linked id; absent error or exact boolean false |
| pair filenames | JSONL/meta basename | required | exact `agent-<safe-id>.jsonl` and `agent-<same-id>.meta.json` |
| meta | `toolUseId`, `agentType`, `spawnDepth` | required | non-empty linked strings; exact integer 1; actor/type linkage exact |
| subagent row | `agentId`, `sessionId`, `isSidechain`, `timestamp` | required | filename actor; shared non-empty session; boolean true; strictly increasing unique timestamps across every row |
| subagent message | `content`, assistant `model`, assistant `usage` | required when message exists | object-list content; every `type: text` value exact string; exact served model; usage object; tool calls only from assistant and tool results only from user |
| reviewer text | assistant text blocks | exactly one verdict event | exactly one text block in verdict-bearing event; whole-event six-line full match after CR/CRLF and one terminal-newline normalization; must be final assistant text |
| snapshot row | `ts`, `event`, `tool`, `tool_use_id`, `agent_id`, `subagent_type`, `head`, `files` | required | finite positive number; pinned enums; non-empty ids/head; nullable typed actor/subtype; string map; timestamps/keys unique and ordered |
| reviewer snapshots | call-linked events | required by pinned tool policy | every shared call id has reviewer actor and exact tool; Agent/Task/Bash exact Pre+Post, edit tools exact Post; bidirectional cardinality |
| score record | `run_id`, `arm`, `revision`, `evidence_bundle` | required strings | known arm/revision, safe bundle, raw run id equality |
| score record | `elapsed_seconds` | required exact int/float, not bool | finite and nonnegative |
| score record | `changed_paths` | required non-empty list | every item non-empty string |
| score record | validation outcomes | required strings | enum PASS/FAIL; either FAIL maps to scored FAIL and reviewer PASS is disclosed as contradiction |
| score record | `rework_count` | required exact integer, not bool | nonnegative |
| batch | records / run ids / arms | required campaign cardinality | run id exact non-empty string before duplicate-set use; malformed rows disclosed UNSCORABLE; unique ids across arms; exact N per arm; any UNSCORABLE leaves INCOMPLETE; unsupported host leaves BLOCKED |

Malformed types, absent required fields, present-invalid optional fields, ambiguity,
hash/path/inventory mismatch and contradictions not assigned scored FAIL above are
`UNSCORABLE`. The adapter does not authenticate the producer: self-hashes prove only
internal bundle integrity. Host binary integrity, pre-seal filesystem tampering, hook
correctness, free-form tool-output truth and behavioral generalization remain outside
this static contract and keep behavioral qualification NOT RUN/BLOCKED.
