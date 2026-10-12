# Shode House 4.0.1 host notes

All 6 role sources and 20 skills are preserved under knowledge/. The agent files, skill roots and commands at the plugin root are those sources with plugin-root and `./`/`../` references re-pointed to their knowledge/ copies, plus a generated resolution footer; `/ask` is the pinned wrapper of the ask skill. Use ask as the entry.

- Claude Code: `.claude-plugin` manifest, flat skills, agents, the authored commands (`/ask` is the entry). The router style delegates to native registered agents.
- Codex: the `ask` skill coordinates genuine separate workers using the six generated role contracts. After the user trusts the hooks and Python 3 is available, lifecycle hooks restore context after compaction and guard direct structured writes. Hook text is not authentication; shell commands and per-role model, tool and scope isolation stay ADVISORY-ONLY.
- Cursor: skills run in one session; there is no verified router. Never replace delegation with role-play or claim independent review without a genuine separate worker.
- On hosts without the router style the safety floor is in the `ask` skill (other shode-house skills point to it). Keep the host's own command approval and sandbox enabled for shell and MCP actions.
- Main-tree manifests: root portable `plugin.json`, `.codex-plugin` compatibility fallback and `.cursor-plugin`. The portable manifest carries the OpenAI hook extension; Antigravity uses the separate `plugins/shode-house-antigravity` host artifact without that extension.

Skill discovery does not prove separate workers are available. If delegation is unavailable, report team execution BLOCKED; never replace it with role-play.
No MCP startup is included. Codex lifecycle hooks load only through its explicit manifest.
