"""Pre-registered 4.0.2 routing-battery contract.

The 4.0.2 protocol is an additive frozen revision of the 4.0.1 battery.  These
tests never call a model: runner tests use tests/fake_claude.py and logger
failure tests put a deterministic tee stand-in first on PATH.
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
D401 = ROOT / "eval/scenarios/battery-4.0.1"
D402 = ROOT / "eval/scenarios/battery-4.0.2"
RUN401 = ROOT / "eval/run-battery-4.0.1.sh"
RUN402 = ROOT / "eval/run-battery-4.0.2.sh"
SET401 = D401 / "battery-4.0.1.json"
SET402 = D402 / "battery-4.0.2.json"

# These are the accepted 4.0.1/baseline bytes at protocol fork time.  A 4.0.2
# implementation must add files; updating an old manifest together with old
# content cannot make this test green.
OLD_SHA256 = {
    "eval/FREEZE.sha256": "7cc72299927f28c7db0df400cf99051d89b17b5ec5db6016887d6e8e2f2dadbc",
    "eval/scenarios/golden.json": "28a55abb9d1772ff2f60722def7684bed9ead0e7923b126512bc1e181122014d",
    "eval/scenarios/battery-4.0.1/FREEZE.sha256": "329353eabeadba8bf9587fae6391c2f79b9fb28df1cac1b7ac38fefd8f8447e7",
    "eval/run-battery-4.0.1.sh": "5634112df11061d5a32d8e9f12d4ff2a0066613bdaf5e8ad657747ad8336fe95",
    "eval/scenarios/battery-4.0.1/battery-4.0.1.json": "3b24d3ac1ce2c32ae4721d45b1200b998aa68958030eb02fb986df5e5324d47f",
    "eval/scenarios/battery-4.0.1/README.md": "acea6f60470b3aa1157b0f2209cce249ea689ceb50c8a9466c2bbc070cf7204c",
    "eval/scenarios/battery-4.0.1/check-freeze.sh": "231e82da005b0af2f3a57237cb7da89116ce3c362a4b7e472b62e438386320a7",
    "eval/scenarios/battery-4.0.1/check-domain.py": "80615fb7c4b0428f866845e1bd71d02e20ca62389e4acd62f54b8967884c0a13",
}

NEW_FROZEN = {
    "eval/run-battery-4.0.2.sh",
    "eval/scenarios/battery-4.0.2/battery-4.0.2.json",
    "eval/scenarios/battery-4.0.2/README.md",
    "eval/scenarios/battery-4.0.2/check-freeze.sh",
    "eval/scenarios/battery-4.0.2/check-domain.py",
}

EVAL_ENV = (
    "CLAUDE_BIN", "PLUGIN_REF", "BASE_REF", "ARM_SCOPE", "PROBE_FILE", "PROBE_IDS", "REPEATS", "MAX_RETRY",
    "ALLOW_UNFROZEN", "PROBE_BLOCK_SPAWN", "RUN_TIMEOUT_S", "MAX_BUDGET_USD", "FREEZE_ROOT", "CHECK_ROOT",
    "FAKE_MODE", "FAKE_INFRA_ON", "FAKE_SKILL", "FAKE_PLAN_MODEL", "FAKE_PLAN_DOMAIN", "BATTERY_LOGGER_MODE",
    "BATTERY_LOGGER_SEEN", "BATTERY_LOGGER_RELEASE", "BATTERY_LOGGER_SENTINEL", "GIT_DIR", "GIT_WORK_TREE",
    "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
    "GIT_PREFIX",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean_env(**extra):
    env = {key: value for key, value in os.environ.items() if key not in EVAL_ENV}
    env.update(extra)
    return env


class SurfaceMixin:
    def require_surface(self):
        required = [RUN402, D402 / "FREEZE.sha256", *(ROOT / rel for rel in sorted(NEW_FROZEN) if not rel.startswith("eval/run-"))]
        missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
        self.assertEqual([], missing, "4.0.2 frozen protocol surface is absent/incomplete: " + ", ".join(missing))


class HistoricalIdentityTest(unittest.TestCase):
    def test_4_0_1_runner_manifest_and_baseline_remain_byte_identical(self):
        self.assertEqual(OLD_SHA256, {rel: sha256(ROOT / rel) for rel in OLD_SHA256})
        result = subprocess.run(["bash", str(D401 / "check-freeze.sh")], capture_output=True, text=True, env=clean_env())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


class FrozenRevisionTest(SurfaceMixin, unittest.TestCase):
    def manifest_paths(self, root=ROOT):
        lines = (root / "eval/scenarios/battery-4.0.2/FREEZE.sha256").read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines, "the independent 4.0.2 freeze manifest must not be empty")
        parsed = [line.split("  ", 1) for line in lines]
        self.assertTrue(all(len(parts) == 2 and len(parts[0]) == 64 for parts in parsed), "manifest entries are sha256 + two spaces + path")
        return {parts[1] for parts in parsed}

    def test_new_freeze_is_independent_and_green(self):
        self.require_surface()
        self.assertEqual(NEW_FROZEN, self.manifest_paths())
        self.assertFalse(any("4.0.1" in path for path in self.manifest_paths()), "4.0.2 must not claim 4.0.1 files in its manifest")
        result = subprocess.run(["bash", str(D402 / "check-freeze.sh")], capture_output=True, text=True, env=clean_env())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("battery-4.0.2 freeze OK", result.stdout)

    def tree(self):
        self.require_surface()
        root = Path(tempfile.mkdtemp(prefix="shode-battery-402-freeze.")).resolve()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        copy = NEW_FROZEN | {
            "eval/scenarios/battery-4.0.2/FREEZE.sha256",
            "eval/scenarios/golden.json",
        }
        for rel in copy:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, root / rel)
        return root

    def check(self, root):
        return subprocess.run(
            ["bash", str(root / "eval/scenarios/battery-4.0.2/check-freeze.sh")],
            capture_output=True,
            text=True,
            env=clean_env(FREEZE_ROOT=str(root)),
        )

    def test_new_freeze_rejects_tamper_and_rederived_manifest_does_not_hide_semantic_drift(self):
        root = self.tree()
        green = self.check(root)
        self.assertEqual(0, green.returncode, green.stdout + green.stderr)

        runner = root / "eval/run-battery-4.0.2.sh"
        runner.write_text(runner.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")
        changed = self.check(root)
        self.assertNotEqual(0, changed.returncode)
        self.assertIn("CHANGED eval/run-battery-4.0.2.sh", changed.stdout + changed.stderr)

        shutil.copy2(RUN402, runner)
        battery = root / "eval/scenarios/battery-4.0.2/battery-4.0.2.json"
        battery.write_text(battery.read_text(encoding="utf-8").replace('"agent:operate"', '"agent:build"', 1), encoding="utf-8")
        manifest = root / "eval/scenarios/battery-4.0.2/FREEZE.sha256"
        rewritten = []
        for line in manifest.read_text(encoding="utf-8").splitlines():
            _, rel = line.split("  ", 1)
            rewritten.append(f"{sha256(root / rel)}  {rel}")
        manifest.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
        drift = self.check(root)
        self.assertNotEqual(0, drift.returncode)
        self.assertIn("DERIVATION", drift.stdout + drift.stderr)


class SemanticParityTest(SurfaceMixin, unittest.TestCase):
    def test_scenarios_prompt_bytes_and_domain_scorer_match_4_0_1(self):
        self.require_surface()
        old = json.loads(SET401.read_text(encoding="utf-8"))
        new = json.loads(SET402.read_text(encoding="utf-8"))
        self.assertEqual(old["derived_from"], new["derived_from"])
        self.assertEqual(old["domain_tier"], new["domain_tier"])
        self.assertEqual(old["scenarios"], new["scenarios"], "4.0.2 changes transport/commit protocol, not routing expectations")
        golden = json.loads((ROOT / "eval/scenarios/golden.json").read_text(encoding="utf-8"))["scenarios"]
        golden_prompts = {scenario["id"]: scenario["prompt"] for scenario in golden if scenario.get("kind") == "probe"}
        new_prompts = {scenario["id"]: scenario["prompt"] for scenario in new["scenarios"]}
        self.assertEqual(golden_prompts, new_prompts)
        baseline_manifest = dict(
            reversed(line.split("  ", 1))
            for line in (ROOT / "eval/FREEZE.sha256").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        for prompt in new_prompts.values():
            self.assertIn(prompt, baseline_manifest, prompt + " is not pinned by the historical baseline")
            self.assertEqual(baseline_manifest[prompt], sha256(ROOT / prompt), prompt)

        trace_fd, trace_name = tempfile.mkstemp(prefix="battery-402-domain-", suffix=".jsonl")
        os.close(trace_fd)
        trace = Path(trace_name)
        self.addCleanup(trace.unlink, missing_ok=True)
        events = [
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Task", "input": {
                "subagent_type": "shode-house:plan", "model": "opus", "prompt": "load references/domain/fintech.md"
            }}]}},
            {"type": "result", "subtype": "error_max_turns", "is_error": True, "result": ""},
        ]
        trace.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
        results = []
        for checker in (D401 / "check-domain.py", D402 / "check-domain.py"):
            run = subprocess.run([sys.executable, str(checker), "P15", str(trace)], capture_output=True, text=True, env=clean_env())
            results.append((run.returncode, run.stdout, run.stderr))
        self.assertEqual(results[0], results[1], "4.0.2 domain scoring must be semantically identical")
        self.assertEqual(0, results[1][0], results[1][1] + results[1][2])


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "needs bash + git")
class Runner402Test(SurfaceMixin, unittest.TestCase):
    SENTINEL = "BATTERY-402-PENDING-PAYLOAD-7fd28c"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shode-battery-402-run.")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        fake = self.tmp / "claude"
        fake.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{ROOT}/tests/fake_claude.py" "$@"\n', encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        (self.tmp / "tmp").mkdir()
        self.env = clean_env(CLAUDE_BIN=str(fake), TMPDIR=str(self.tmp / "tmp"))

    def run402(self, out, ids="P02", **extra):
        self.require_surface()
        env = dict(self.env, PROBE_IDS=ids, REPEATS="1", **extra)
        return subprocess.run(["bash", str(RUN402), "sonnet", str(out)], capture_output=True, text=True, env=env, timeout=90)

    def test_batch_run_metadata_and_summary_identify_only_4_0_2(self):
        out = self.tmp / "batch402"
        done = self.run402(out, ids="P02 P03")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        batch = json.loads((out / "BATCH.json").read_text(encoding="utf-8"))
        self.assertEqual("4.0.2", batch["battery"])
        self.assertTrue(batch["scenarios"].endswith("eval/scenarios/battery-4.0.2/battery-4.0.2.json"))
        self.assertEqual(sha256(SET402), batch["scenarios_sha256"])
        meta = json.loads((out / "P02/r1/meta.json").read_text(encoding="utf-8"))
        self.assertEqual(sha256(SET402), meta["sha256"]["scenarios"])
        self.assertEqual("4.0.2", meta["battery"], "each result must carry the protocol identity, not rely only on its directory")
        self.assertIn("SUMMARY battery-4.0.2", done.stdout)
        self.assertNotIn("battery-4.0.1", done.stdout + done.stderr + json.dumps(batch, sort_keys=True))
        rows = [tuple(line.split("\t")[:3]) for line in (out / "SUMMARY.tsv").read_text(encoding="utf-8").splitlines()[1:]]
        self.assertEqual([("P02", "r1", "0"), ("P03", "r1", "1")], rows, "the unchanged scorer preserves pass/fail semantics")

    def test_4_0_1_and_4_0_2_outputs_cannot_resume_or_mix_in_either_direction(self):
        self.require_surface()
        out401 = self.tmp / "made-by-401"
        env = dict(self.env, PROBE_IDS="P02", REPEATS="1")
        made401 = subprocess.run(["bash", str(RUN401), "sonnet", str(out401)], capture_output=True, text=True, env=env, timeout=90)
        self.assertEqual(0, made401.returncode, made401.stdout + made401.stderr)
        before401 = {str(path.relative_to(out401)): sha256(path) for path in out401.rglob("*") if path.is_file()}
        reject402 = self.run402(out401)
        self.assertEqual(3, reject402.returncode, reject402.stdout + reject402.stderr)
        self.assertIn("different batch", reject402.stderr)
        self.assertEqual(before401, {str(path.relative_to(out401)): sha256(path) for path in out401.rglob("*") if path.is_file()})

        out402 = self.tmp / "made-by-402"
        made402 = self.run402(out402)
        self.assertEqual(0, made402.returncode, made402.stdout + made402.stderr)
        before402 = {str(path.relative_to(out402)): sha256(path) for path in out402.rglob("*") if path.is_file()}
        reject401 = subprocess.run(["bash", str(RUN401), "sonnet", str(out402)], capture_output=True, text=True, env=env, timeout=90)
        self.assertEqual(3, reject401.returncode, reject401.stdout + reject401.stderr)
        self.assertIn("different batch", reject401.stderr)
        self.assertEqual(before402, {str(path.relative_to(out402)): sha256(path) for path in out402.rglob("*") if path.is_file()})

    def install_tee(self):
        """Install a line-oriented tee fault injector; ordinary lines still reach both sinks."""
        bindir = self.tmp / "logger-bin"
        bindir.mkdir(exist_ok=True)
        tee = bindir / "tee"
        tee.write_text(
            f"#!{sys.executable}\n"
            "import os, sys, time\n"
            "args = sys.argv[1:]\n"
            "log = args[-1]\n"
            "mode = os.environ.get('BATTERY_LOGGER_MODE', 'ok')\n"
            "sentinel = os.environ['BATTERY_LOGGER_SENTINEL'].encode()\n"
            "seen = os.environ.get('BATTERY_LOGGER_SEEN')\n"
            "release = os.environ.get('BATTERY_LOGGER_RELEASE')\n"
            "with open(log, 'ab', buffering=0) as durable:\n"
            "  for line in sys.stdin.buffer:\n"
            "    if sentinel in line:\n"
            "      if seen:\n"
            "        open(seen, 'wb').close()\n"
            "      if mode == 'fail-before':\n"
            "        sys.exit(71)\n"
            "      if mode == 'fail-during':\n"
            "        durable.write(line[:max(1, len(line)//2)]); os.fsync(durable.fileno()); sys.exit(72)\n"
            "      if mode == 'delay':\n"
            "        end = time.monotonic() + 20\n"
            "        while not os.path.exists(release):\n"
            "          if time.monotonic() > end: sys.exit(73)\n"
            "          time.sleep(.01)\n"
            "    durable.write(line); os.fsync(durable.fileno())\n"
            "    sys.stdout.buffer.write(line); sys.stdout.buffer.flush()\n",
            encoding="utf-8",
        )
        tee.chmod(0o700)
        return str(bindir) + os.pathsep + os.environ.get("PATH", "")

    def install_post_copy_fault(self, command, target, exit_code):
        """Fail one exact post-copy command without perturbing earlier runner operations."""
        bindir = self.tmp / (command + "-fault-bin")
        bindir.mkdir(exist_ok=True)
        marker = self.tmp / (command + ".failed-once")
        wrapper = bindir / command
        if command == "python3":
            real = sys.executable
            match = "sys.argv[1:] == ['-', target]"
        else:
            real = shutil.which(command)
            self.assertIsNotNone(real, command + " is required for fault injection")
            match = "sys.argv[1:] == ['-f', target]"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\n"
            f"target = {str(target)!r}\n"
            f"marker = {str(marker)!r}\n"
            f"if {match} and not os.path.exists(marker):\n"
            "  open(marker, 'wb').close()\n"
            f"  sys.exit({exit_code})\n"
            f"os.execv({real!r}, [{real!r}, *sys.argv[1:]])\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        return {
            "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
            "fault_marker": marker,
        }

    def install_commit_cleanup_fault(self, out):
        """Stop after committed pending unlink but before synced sidecar cleanup."""
        bindir = self.tmp / "commit-cleanup-fault-bin"
        bindir.mkdir(exist_ok=True)
        marker = self.tmp / "commit-cleanup.failed-once"
        pending = out / ".redact-pending.out"
        log = out / "log.txt"
        state = out / ".redact-pending.commit"
        wrapper = bindir / "python3"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\n"
            f"marker = {str(marker)!r}\n"
            f"target = {['-', 'cleanup', str(pending), str(log), str(state)]!r}\n"
            "if sys.argv[1:] == target and not os.path.exists(marker):\n"
            "  open(marker, 'wb').close()\n"
            "  sys.exit(76)\n"
            f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        return {
            "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
            "fault_marker": marker,
            "state": state,
        }

    def pending_batch(self, name):
        out = self.tmp / name
        initial = self.run402(out)
        self.assertEqual(0, initial.returncode, initial.stdout + initial.stderr)
        pending = out / ".redact-pending.out"
        pending.write_text(self.SENTINEL + "\n", encoding="utf-8")
        pending.chmod(0o600)
        return out, pending

    def logger_env(self, mode):
        return {
            "PATH": self.install_tee(),
            "BATTERY_LOGGER_MODE": mode,
            "BATTERY_LOGGER_SENTINEL": self.SENTINEL,
            "BATTERY_LOGGER_SEEN": str(self.tmp / (mode + ".seen")),
            "BATTERY_LOGGER_RELEASE": str(self.tmp / (mode + ".release")),
        }

    def test_logger_failure_before_or_during_payload_commit_is_nonzero_and_preserves_buffer_for_retry(self):
        for mode in ("fail-before", "fail-during"):
            with self.subTest(mode):
                out, pending = self.pending_batch(mode)
                original = pending.read_bytes()
                failed = self.run402(out, **self.logger_env(mode))
                self.assertNotEqual(0, failed.returncode, "logger failure must fail the invocation")
                self.assertTrue(pending.is_file(), "uncommitted payload remains resumable")
                self.assertEqual(original, pending.read_bytes(), "failure never truncates or rewrites the pending payload")
                self.assertEqual(0, (out / "log.txt").read_text(encoding="utf-8").count(self.SENTINEL), "no full durable payload was committed")
                retried = self.run402(out)
                self.assertEqual(0, retried.returncode, retried.stdout + retried.stderr)
                self.assertFalse(pending.exists())
                self.assertEqual(1, (out / "log.txt").read_text(encoding="utf-8").count(self.SENTINEL))
                self.assertEqual(
                    1,
                    (failed.stdout + failed.stderr + retried.stdout + retried.stderr).count(self.SENTINEL),
                    "a partial logger failure remains resumable without a duplicate console delivery",
                )

    def test_post_copy_fsync_failure_recovers_once_without_replaying_either_sink(self):
        out, pending = self.pending_batch("post-copy-fsync")
        payload = pending.read_bytes()
        fault = self.install_post_copy_fault("python3", out / "log.txt", 74)
        failed = self.run402(out, PATH=fault["PATH"])
        self.assertNotEqual(0, failed.returncode, "post-copy fsync failure must fail closed")
        self.assertTrue(fault["fault_marker"].is_file(), "the test must reach the intended fsync fault")
        self.assertTrue(pending.is_file(), "the pending/transaction source must survive for restart recovery")
        self.assertEqual(payload, pending.read_bytes(), "the recovery source remains byte-identical")
        self.assertEqual(1, (out / "log.txt").read_bytes().count(payload), "the failed attempt completed the log copy")
        self.assertEqual(1, (failed.stdout + failed.stderr).encode().count(payload), "the failed attempt completed console delivery")

        retried = self.run402(out)
        self.assertEqual(0, retried.returncode, retried.stdout + retried.stderr)
        self.assertFalse(pending.exists(), "restart finalizes the recovered transaction")
        observed = (
            (out / "log.txt").read_bytes().count(payload),
            (failed.stdout + failed.stderr + retried.stdout + retried.stderr).encode().count(payload),
        )
        self.assertEqual((1, 1), observed, "failed attempt plus restart must deliver one full payload to each sink overall")

    def test_committed_payload_unlink_failure_recovers_once_without_replaying_either_sink(self):
        out, pending = self.pending_batch("committed-pending-unlink")
        payload = pending.read_bytes()
        fault = self.install_post_copy_fault("rm", pending, 75)
        failed = self.run402(out, PATH=fault["PATH"])
        self.assertNotEqual(0, failed.returncode, "committed-pending unlink failure must fail closed")
        self.assertTrue(fault["fault_marker"].is_file(), "the test must reach the intended pending unlink fault")
        self.assertTrue(pending.is_file(), "committed-but-pending state must survive the failed finalization")
        self.assertEqual(payload, pending.read_bytes(), "restart recovery retains the exact transaction payload")
        self.assertEqual(1, (out / "log.txt").read_bytes().count(payload), "the failed attempt durably committed the log payload")
        self.assertEqual(1, (failed.stdout + failed.stderr).encode().count(payload), "the failed attempt completed console delivery")

        retried = self.run402(out)
        self.assertEqual(0, retried.returncode, retried.stdout + retried.stderr)
        self.assertFalse(pending.exists(), "restart clears committed pending state")
        observed = (
            (out / "log.txt").read_bytes().count(payload),
            (failed.stdout + failed.stderr + retried.stdout + retried.stderr).encode().count(payload),
        )
        self.assertEqual((1, 1), observed, "committed recovery must finalize without replaying either sink")

    def test_restart_after_pending_unlink_before_sidecar_cleanup_finishes_once(self):
        out, pending = self.pending_batch("post-unlink-crash")
        payload = pending.read_bytes()
        fault = self.install_commit_cleanup_fault(out)
        failed = self.run402(out, PATH=fault["PATH"])
        self.assertNotEqual(0, failed.returncode, "injected post-unlink interruption must stop the invocation")
        self.assertTrue(fault["fault_marker"].is_file(), "the test must reach synced sidecar cleanup")
        self.assertFalse(pending.exists(), "the crash window begins only after committed pending unlink")
        self.assertTrue(fault["state"].is_file(), "the synced recovery sidecar must survive the interruption")
        self.assertEqual(1, (out / "log.txt").read_bytes().count(payload))
        self.assertEqual(1, (failed.stdout + failed.stderr).encode().count(payload))

        restarted = self.run402(out)
        self.assertEqual(0, restarted.returncode, restarted.stdout + restarted.stderr)
        self.assertFalse(fault["state"].exists(), "restart must finish synced sidecar cleanup")
        observed = (
            (out / "log.txt").read_bytes().count(payload),
            (failed.stdout + failed.stderr + restarted.stdout + restarted.stderr).encode().count(payload),
        )
        self.assertEqual((1, 1), observed, "restart must not replay either committed sink")

    def test_success_deletes_pending_only_after_logger_durable_completion_and_copies_once_to_each_sink(self):
        out, pending = self.pending_batch("delay")
        extra = self.logger_env("delay")
        env = dict(self.env, PROBE_IDS="P02", REPEATS="1", **extra)
        proc = subprocess.Popen(
            ["bash", str(RUN402), "sonnet", str(out)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        def stop_process():
            Path(extra["BATTERY_LOGGER_RELEASE"]).touch()
            if proc.poll() is None:
                proc.kill()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.addCleanup(stop_process)
        seen = Path(extra["BATTERY_LOGGER_SEEN"])
        deadline = time.monotonic() + 15
        while not seen.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(seen.exists(), "logger never received the actual pending payload")
        self.assertIsNone(proc.poll(), "runner returned before logger commit completed")
        self.assertTrue(pending.is_file(), "pending payload was deleted before durable logger completion")
        self.assertEqual(0, (out / "log.txt").read_text(encoding="utf-8").count(self.SENTINEL))
        Path(extra["BATTERY_LOGGER_RELEASE"]).touch()
        stdout, stderr = proc.communicate(timeout=30)
        self.assertEqual(0, proc.returncode, stdout + stderr)
        self.assertFalse(pending.exists())
        self.assertEqual(1, (out / "log.txt").read_text(encoding="utf-8").count(self.SENTINEL), "one durable log copy")
        self.assertEqual(1, (stdout + stderr).count(self.SENTINEL), "one console copy")

    def test_runner_has_no_probe_or_timeout_inference_for_payload_ownership(self):
        self.require_surface()
        text = RUN402.read_text(encoding="utf-8").lower()
        for forbidden in ("logger probe", "logger_observe", "persist_battery_console_if_logger_unavailable"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
