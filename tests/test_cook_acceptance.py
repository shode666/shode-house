"""Structural acceptance for the planned single public ``cook`` entry.

This module inspects the real generated package produced by ``pack-team.py``.
It does not claim native host discovery or behavioral routing. Those checks
remain BLOCKED until the repository exposes a runnable entry interface or a
supported host can load the package.

Behavioral checklist to run through that real interface, without a test-only
production shim:

* consultation: answer/read only; no project write;
* init interactive and quick: exercise fresh, existing ``.git`` directory,
  worktree ``.git`` file, and source-only repository fixtures;
* init preserves every pre-existing source, CI, tracker and guidance file;
* spec-only stops before implementation;
* implementation follows the already-authorized scope and existing gates;
* review-only leaves the target tree byte-for-byte unchanged;
* resume reads the existing checkpoint and does not create duplicate work;
* ambiguous read/edit/publish authority stays read-only or asks at the boundary.

Native checklist: load the built package in the supported Codex host, confirm
that ``cook`` is discoverable once, invoke it through the host's skill UI, and
record the worker/delegation trace. Mentioning ``cook`` in a prompt is not this
proof.
"""

import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
LEGACY_PUBLIC_NAMES = {"ask", "consult", "design-system", "implement", "init", "review"}


def load_pack():
    spec = importlib.util.spec_from_file_location(
        "pack_team_cook_acceptance", ROOT / "scripts/pack-team.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load_pack()


def stem(path):
    return Path(path).parent.name if path.endswith("/SKILL.md") else Path(path).stem


def named_ask(path):
    parts = Path(path.removeprefix("./")).parts
    return "ask" in parts or (parts and Path(parts[-1]).stem == "ask")


def markdown_closure(start):
    """Text reachable through ordinary relative Markdown links from ``start``."""
    pending = [start.resolve()]
    seen = set()
    bodies = []
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        text = path.read_text()
        bodies.append(text)
        for target in re.findall(r"\[[^]]*\]\(([^)#]+\.md)(?:#[^)]+)?\)", text):
            candidate = (path.parent / target).resolve()
            if candidate.is_relative_to(ROOT) and candidate.is_file():
                pending.append(candidate)
    return "\n".join(bodies)


def allowlisted_files():
    files = []
    for raw in (ROOT / ".pack-allowlist").read_text().splitlines():
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        path = ROOT / name
        files.extend(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else files.append(path)
    return files


class CookPackageStructuralAcceptanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.entries = pack.unified_payload()
        cls.claude = json.loads(cls.entries[".claude-plugin/plugin.json"])
        cls.codex = json.loads(cls.entries[".codex-plugin/plugin.json"])
        cls.portable = json.loads(cls.entries["plugin.json"])

    def test_generated_package_has_exactly_one_router_skill_and_no_wrapper(self):
        self.assertIn("skills/cook/SKILL.md", self.entries)
        self.assertNotIn("commands/cook.md", self.entries)
        self.assertEqual([], [path for path in self.entries if path.startswith("commands/")])

    def test_each_host_primary_entry_is_cook_and_resolves_in_the_package(self):
        codex_entries = [
            self.codex["extensions"]["com.openai"]["onboardingSkill"],
            self.portable["extensions"]["com.openai"]["onboardingSkill"],
        ]
        for advertised in codex_entries:
            self.assertEqual("cook", stem(advertised))
            self.assertIn(advertised.removeprefix("./"), self.entries)

        self.assertEqual([], self.claude.get("commands", []))

    def test_legacy_public_commands_are_not_advertised(self):
        advertised = {stem(path) for path in self.claude.get("commands", [])}
        self.assertFalse(advertised & LEGACY_PUBLIC_NAMES, advertised)

        flat_skills = {
            Path(path).parent.name
            for path in self.entries
            if re.fullmatch(r"skills/[^/]+/SKILL\.md", path)
        }
        self.assertFalse(flat_skills & LEGACY_PUBLIC_NAMES, flat_skills)

    def test_cook_is_the_router_and_no_ask_file_remains(self):
        self.assertIn("skills/cook/SKILL.md", self.entries)
        self.assertEqual([], [path for path in self.entries if named_ask(path)])

        source_roots = [ROOT / "commands", *(ROOT / "skills" / name for name in
                       ("workflow", "ops", "ui", "style", "discipline"))]
        source_paths = [p.relative_to(ROOT).as_posix() for root in source_roots for p in root.rglob("*")]
        self.assertEqual([], [path for path in source_paths if named_ask(path)])

        generated_roots = [ROOT / "plugins/shode-house", ROOT / "plugins/shode-house-antigravity"]
        generated_paths = [p.relative_to(ROOT).as_posix() for root in generated_roots for p in root.rglob("*")]
        self.assertEqual([], [path for path in generated_paths if named_ask(path)])

        packed_paths = [p.relative_to(ROOT).as_posix() for p in allowlisted_files()]
        self.assertEqual([], [path for path in packed_paths if named_ask(path)])

    def test_cook_router_retains_six_intent_vocabulary(self):
        source = ROOT / "skills/workflow/cook/SKILL.md"
        self.assertTrue(source.is_file(), source)
        cook = source.read_text().lower()
        for intent in ("consult", "init", "spec", "implement", "review", "resum"):
            self.assertRegex(cook, intent)

    def test_old_command_behaviors_remain_reachable_from_cook(self):
        source = ROOT / "skills/workflow/cook/SKILL.md"
        self.assertTrue(source.is_file(), source)
        reachable = markdown_closure(source).lower()
        for contract in (
            "interactive", "--quick", "brownfield",
            "--stop", "--estimate",
            "review", "read-only",
        ):
            self.assertIn(contract, reachable)


if __name__ == "__main__":
    unittest.main()
