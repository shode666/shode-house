#!/usr/bin/env bash
# 4.0.2 routing-probe battery runner: the P01..P47 prompts mapped to the 6 types (eval/scenarios/battery-4.0.2/). A copy of the
# run-probes.sh logic under a new name; eval/run-probes.sh, eval/run-lib.sh, eval/scenarios/golden.json and every file pinned in
# eval/FREEZE.sha256 stay untouched (they are the 3.17 / 4.0.0 baseline). This script records; it does not judge.
#   bash eval/run-battery-4.0.2.sh [model=sonnet] [out-dir]
#   REPEATS=5                     runs per probe (default 5 = the N of the P01..P47 baseline), round-robin: all ids for r1, then r2, ...
#   PROBE_IDS="P01 P02" | all     default = every probe without `not_applicable` (46; P21 is refused)
#   PLUGIN_REF=<git ref>          plugin under test = that git ref (read-only git archive); default = working tree
#                                 (no arm-diff guard: this battery compares nothing by itself; compare AGG.tsv with the baseline's)
#   PROBE_FILE is not supported (the battery is the pinned file, not an external set)
# layout : <out>/<id>/r<k>/{run.jsonl,run.files,meta.json,score.txt,score.json,tools-seen.txt,prompt.txt,...}; the 7 domain probes also
#          get domain-check.txt (check-domain.py: which domain reference the plan spawn names, requested model tier)
#          <out>/BATCH.json . <out>/SUMMARY.tsv . <out>/AGG.tsv . <out>/log.txt
# resume : as run-probes.sh (same SAME-out-dir rule, crash retry, infra stop, exit codes 0/2/3/5)
# guards : refuses to start unless the old freeze (bash eval/check-freeze.sh) AND the battery freeze
#          (bash eval/scenarios/battery-4.0.2/check-freeze.sh) are green; ALLOW_UNFROZEN=1 only for dry runs.
# owner-only: umask 077 before anything exists (dirs 0700, files 0600); a symlinked out-dir is refused; an existing out-dir is locked
#          down before any run (eval/redact_derived.py lockdown, as eval/run-core.sh): every dir 0700, every file 0600, or exit 4 with
#          nothing changed (symlink / special / hard-linked / foreign entry).
# redact : as eval/run-core.sh, after each run the derived files (tools-seen.txt score.txt score.json meta.json, domain-check.txt),
#          the buffered console output of the run, SUMMARY.tsv and AGG.tsv are redacted in place (eval/redact_derived.py); run.jsonl
#          stays byte-exact (sha256 in redaction.json). Redaction failure = exit 4, no further run. <out>/.redact-pending names the
#          run in flight: the next invocation seals it before anything else. The actual pending payload is sent through one owned FIFO
#          logger, whose process is awaited and whose log is fsynced before the byte-identical buffer is deleted. Logger failure is
#          fail-closed and leaves the pending payload for retry. run_one (frozen run-lib.sh) is wrapped, not edited.
# exit   : 0 = every slot has a scored run (0/1) . 2 = some slot unscorable/incomplete . 3 = refused . 4 = redaction failed or the
#          out-dir cannot be made owner-only . 5 = stopped (infra)
umask 077   # before any file or directory of the batch exists (SEC-13): raw and derived evidence stay owner-only
. "$(dirname "${BASH_SOURCE[0]}")/run-lib.sh"
# run-lib.sh picks golden.json; this runner scores the 4.0.2 battery (prompt paths are repo-relative, as in golden.json)
[ -z "${PROBE_FILE:-}" ] || die "PROBE_FILE is not supported by the 4.0.2 battery runner (use eval/run-probes.sh for an external set)"
BATTERY_DIR="$REPO/eval/scenarios/battery-4.0.2"
SCENARIOS="$BATTERY_DIR/battery-4.0.2.json"; PROMPT_BASE="$REPO"
[ -f "$SCENARIOS" ] || die "missing $SCENARIOS"
MODEL="${1:-sonnet}"
OUT="${2:-$REPO/outputs/eval-4.0.2/battery/$MODEL-$(date -u +%Y%m%dT%H%M%SZ)}"
REPEATS="${REPEATS:-5}"; MAX_RETRY="${MAX_RETRY:-1}"
case "$REPEATS" in ''|*[!0-9]*|0) die "REPEATS must be a positive integer" ;; esac
IDS="${PROBE_IDS:-all}"
ALL_OK="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1],encoding="utf-8"));print(" ".join(s["id"] for s in (d["scenarios"] if isinstance(d,dict) else d) if s.get("kind")=="probe" and not s.get("not_applicable")))' "$SCENARIOS")" || die "cannot read $SCENARIOS"
if [ "$IDS" = all ]; then IDS="$ALL_OK"; fi
for ID in $IDS; do
  case " $ALL_OK " in *" $ID "*) ;; *) die "$ID is not a runnable probe in $SCENARIOS (unknown id or not_applicable)" ;; esac
done
"$REPO/eval/check-freeze.sh" >/dev/null 2>&1; FREEZE_RC=$?
bash "$BATTERY_DIR/check-freeze.sh" >/dev/null 2>&1 || FREEZE_RC=1
[ "$FREEZE_RC" = 0 ] || [ "${ALLOW_UNFROZEN:-0}" = 1 ] || die "frozen files changed (bash eval/check-freeze.sh; bash eval/scenarios/battery-4.0.2/check-freeze.sh); set ALLOW_UNFROZEN=1 only for dry runs"
preflight
ARM_DIFF="not-applicable"
REDACT="$REPO/eval/redact_derived.py"
redact_fail() { echo "!! STOPPED: redaction failed ($*). Fail-closed: no further run." >&2
                echo "!! Nothing under the out-dir is final; fix the redactor and re-invoke the same command." >&2; exit 4; }
[ -f "$REDACT" ] && [ -f "$REPO/eval/evidence_redact.py" ] || redact_fail "missing eval/redact_derived.py or eval/evidence_redact.py"
python3 "$REDACT" selftest || redact_fail "selftest"

BATCH="$(python3 - "$SCENARIOS" <<PY
import hashlib, json, sys
print(json.dumps({"model": "$MODEL", "plugin_ref": "${PLUGIN_REF:-WORKTREE}", "plugin_sha": "$PLUGIN_SHA",
  "plugin_dirty": "$PLUGIN_DIRTY" == "true", "scenarios": sys.argv[1],
  "scenarios_sha256": hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest(), "cli_version": "$CLI_VERSION",
  "spawn_block": "${PROBE_BLOCK_SPAWN:-1}", "frozen": $FREEZE_RC == 0, "arm_diff": "$ARM_DIFF", "battery": "4.0.2"}, sort_keys=True))
PY
)" || die "cannot build batch identity"
[ ! -L "$OUT" ] || die "refuse: $OUT is a symlink"
if [ -e "$OUT" ]; then
  [ -f "$OUT/BATCH.json" ] || die "refuse: $OUT exists and is not a probe batch (no BATCH.json)"
  [ "$(cat "$OUT/BATCH.json")" = "$BATCH" ] || die "refuse: $OUT belongs to a different batch (model/plugin/scenarios/CLI differ); use a new directory"
  echo "== resuming batch $OUT"
else
  mkdir -p "$OUT" || die "cannot create $OUT"
  printf '%s\n' "$BATCH" > "$OUT/BATCH.json"
fi
OUT="$(cd "$OUT" && pwd -P)"
# a batch begun before umask 077 (or touched by hand): every dir -> 0700, every file -> 0600 before any run; a symlink / special /
# hard-linked / foreign entry refuses the batch with nothing changed
python3 "$REDACT" lockdown "$OUT" || { echo "!! STOPPED: the out-dir cannot be made owner-only (reason above). Nothing ran." >&2
  echo "!! Inspect it by hand (ls -laR), or start a NEW out-dir." >&2; exit 4; }
PENDING="$OUT/.redact-pending"; PENDOUT="$OUT/.redact-pending.out"; COMMIT_STATE="$OUT/.redact-pending.commit"
exec 7>&1 8>&2
LOGGER_TMP="$(mktemp -d "$TMPROOT/shode-battery-402-logger.XXXXXX")" || redact_fail "cannot create logger workspace"
LOGGER_ACTIVE=0; LOGGER_SEQ=0; LOGGER_FIFO=""; LOGGER_PID=""

# Each logger segment has one FIFO writer and one owned tee process. Closing the
# writer and waiting for that exact pid is the completion signal; no observation
# deadline or side-channel probe decides ownership of the pending payload.
logger_start() {
  LOGGER_SEQ=$((LOGGER_SEQ + 1)); LOGGER_FIFO="$LOGGER_TMP/stream.$LOGGER_SEQ"
  mkfifo "$LOGGER_FIFO" || return 1
  tee -a "$OUT/log.txt" < "$LOGGER_FIFO" >&7 2>&8 & LOGGER_PID=$!
  exec 3>"$LOGGER_FIFO" || { kill "$LOGGER_PID" 2>/dev/null; wait "$LOGGER_PID" 2>/dev/null; return 1; }
  exec 1>&3 2>&1
  LOGGER_ACTIVE=1
}
logger_stop() {
  local rc
  [ "$LOGGER_ACTIVE" = 1 ] || return 0
  exec 1>&7 2>&8
  exec 3>&-
  wait "$LOGGER_PID"; rc=$?
  LOGGER_ACTIVE=0
  rm -f "$LOGGER_FIFO"
  return "$rc"
}
fsync_log() {
  python3 - "$OUT/log.txt" <<'PY'
import os, stat, sys
path = sys.argv[1]
before = os.lstat(path)
if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.geteuid() or before.st_mode & 0o077:
    raise SystemExit("refuse to fsync an unsafe log")
fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
try:
    after = os.fstat(fd)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise SystemExit("log identity changed while opening")
    os.fsync(fd)
finally:
    os.close(fd)
PY
}
# Durable state for the actual pending payload.  It pins both file identities,
# the pre-append log boundary and hashes of the payload/log prefix.  Recovery
# can therefore roll back only a proven partial append, or finish a proven
# completed delivery without sending its bytes through either sink again.
commit_state() {
  python3 - "$1" "$PENDOUT" "$OUT/log.txt" "$COMMIT_STATE" <<'PY'
import hashlib, json, os, stat, sys

op, pending_path, log_path, state_path = sys.argv[1:]
directory = os.path.dirname(state_path)
nofollow = getattr(os, "O_NOFOLLOW", 0)


def fail(message):
    raise SystemExit("commit state: " + message)


def fsync_directory():
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def open_owned_regular(path, flags):
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        fail("missing " + path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.geteuid():
        fail("not one owner-only regular file: " + path)
    if before.st_mode & 0o077:
        fail("group/world-accessible file: " + path)
    try:
        fd = os.open(path, flags | nofollow)
    except OSError as exc:
        fail("cannot open %s: %s" % (path, exc))
    after = os.fstat(fd)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or not stat.S_ISREG(after.st_mode):
        os.close(fd)
        fail("file identity changed while opening " + path)
    return fd, after


def read_all(fd, limit=None):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks, total = [], 0
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if limit is not None and total > limit:
            fail("state file is too large")
        chunks.append(chunk)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_state(data, create=False):
    raw = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if create:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(state_path, flags | nofollow, 0o600)
        try:
            view = memoryview(raw)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        tmp = state_path + ".tmp.%d" % os.getpid()
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600)
        try:
            view = memoryview(raw)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, state_path)
    fsync_directory()


def remove_state():
    os.unlink(state_path)
    fsync_directory()


def load_state():
    fd, _ = open_owned_regular(state_path, os.O_RDONLY)
    try:
        try:
            data = json.loads(read_all(fd, 16384).decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail("invalid JSON: " + str(exc))
    finally:
        os.close(fd)
    keys = {"version", "phase", "pending", "log"}
    if not isinstance(data, dict) or set(data) != keys or data.get("version") != 1:
        fail("invalid schema/version")
    if data.get("phase") not in ("prepared", "copied", "synced"):
        fail("invalid phase")
    p, log = data.get("pending"), data.get("log")
    pkeys = {"path", "dev", "ino", "size", "sha256"}
    lkeys = {"path", "dev", "ino", "offset", "prefix_sha256"}
    if not isinstance(p, dict) or set(p) != pkeys or not isinstance(log, dict) or set(log) != lkeys:
        fail("invalid identity schema")
    if p.get("path") != pending_path or log.get("path") != log_path:
        fail("path does not match this batch")
    ints = (p.get("dev"), p.get("ino"), p.get("size"), log.get("dev"), log.get("ino"), log.get("offset"))
    if any(not isinstance(value, int) or value < 0 for value in ints):
        fail("invalid identity/offset")
    for value in (p.get("sha256"), log.get("prefix_sha256")):
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            fail("invalid hash")
    return data


def validate_pending(data, allow_missing=False):
    try:
        fd, st = open_owned_regular(pending_path, os.O_RDONLY)
    except SystemExit:
        if allow_missing and not os.path.lexists(pending_path):
            return None
        raise
    try:
        payload = read_all(fd)
    finally:
        os.close(fd)
    want = data["pending"]
    if (st.st_dev, st.st_ino, len(payload), digest(payload)) != (want["dev"], want["ino"], want["size"], want["sha256"]):
        fail("pending payload identity/hash changed")
    return payload


def validate_log(data):
    fd, st = open_owned_regular(log_path, os.O_RDWR)
    want = data["log"]
    if (st.st_dev, st.st_ino) != (want["dev"], want["ino"]):
        os.close(fd)
        fail("log identity changed")
    content = read_all(fd)
    offset = want["offset"]
    if len(content) < offset or digest(content[:offset]) != want["prefix_sha256"]:
        os.close(fd)
        fail("log prefix/boundary changed")
    return fd, content


if op == "prepare":
    if os.path.lexists(state_path):
        fail("state already exists")
    pfd, pst = open_owned_regular(pending_path, os.O_RDONLY)
    try:
        payload = read_all(pfd)
    finally:
        os.close(pfd)
    lfd, lst = open_owned_regular(log_path, os.O_RDONLY)
    try:
        prefix = read_all(lfd)
    finally:
        os.close(lfd)
    state = {
        "version": 1,
        "phase": "prepared",
        "pending": {"path": pending_path, "dev": pst.st_dev, "ino": pst.st_ino,
                    "size": len(payload), "sha256": digest(payload)},
        "log": {"path": log_path, "dev": lst.st_dev, "ino": lst.st_ino,
                "offset": len(prefix), "prefix_sha256": digest(prefix)},
    }
    write_state(state, create=True)
    raise SystemExit(0)

if op == "recover" and not os.path.lexists(state_path):
    print("none")
    raise SystemExit(0)

state = load_state()
phase = state["phase"]
payload = validate_pending(state, allow_missing=(phase == "synced"))
lfd, log_content = validate_log(state)
offset = state["log"]["offset"]
tail = log_content[offset:]
if phase == "prepared":
    if op != "recover":
        os.close(lfd)
        fail("operation %s is invalid in phase %s" % (op, phase))
    if payload is None or len(tail) > len(payload) or not payload.startswith(tail):
        os.close(lfd)
        fail("unrecognized bytes after prepared log boundary; refusing truncation")
    os.ftruncate(lfd, offset)
    os.fsync(lfd)
    os.close(lfd)
    remove_state()
    print("retry")
elif phase in ("copied", "synced"):
    want = state["pending"]
    if len(tail) != want["size"] or digest(tail) != want["sha256"]:
        os.close(lfd)
        fail("completed log tail does not match pending payload")
    os.close(lfd)
    if op == "recover":
        print(phase)
    elif op == "mark-synced" and phase == "copied":
        state["phase"] = "synced"
        write_state(state)
    elif op == "cleanup" and phase == "synced":
        if os.path.lexists(pending_path):
            fail("pending payload still exists; refusing state cleanup")
        remove_state()
    else:
        fail("operation %s is invalid in phase %s" % (op, phase))
else:
    fail("unknown operation " + op)
PY
}

mark_commit_copied() {
  python3 - "$PENDOUT" "$OUT/log.txt" "$COMMIT_STATE" <<'PY'
import hashlib, json, os, stat, sys
pending_path, log_path, state_path = sys.argv[1:]
nofollow = getattr(os, "O_NOFOLLOW", 0)
def die(msg): raise SystemExit("commit state: " + msg)
def read_regular(path):
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.geteuid() or before.st_mode & 0o077:
        die("unsafe file " + path)
    fd = os.open(path, os.O_RDONLY | nofollow)
    try:
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino): die("identity changed " + path)
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk: break
            chunks.append(chunk)
        return after, b"".join(chunks)
    finally: os.close(fd)
_, raw = read_regular(state_path)
state = json.loads(raw.decode("ascii"))
if state.get("phase") != "prepared" or state["pending"].get("path") != pending_path or state["log"].get("path") != log_path:
    die("invalid prepared state")
pst, payload = read_regular(pending_path)
lst, log = read_regular(log_path)
sha = lambda data: hashlib.sha256(data).hexdigest()
p, l = state["pending"], state["log"]
if (pst.st_dev, pst.st_ino, len(payload), sha(payload)) != (p["dev"], p["ino"], p["size"], p["sha256"]):
    die("pending payload changed")
if (lst.st_dev, lst.st_ino) != (l["dev"], l["ino"]) or len(log) != l["offset"] + p["size"]:
    die("log identity/size changed")
if sha(log[:l["offset"]]) != l["prefix_sha256"] or sha(log[l["offset"]:]) != p["sha256"]:
    die("log tail is not the pending payload")
state["phase"] = "copied"
tmp = state_path + ".tmp.%d" % os.getpid()
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600)
try:
    view = memoryview((json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))
    while view: view = view[os.write(fd, view):]
    os.fsync(fd)
finally: os.close(fd)
os.replace(tmp, state_path)
dfd = os.open(os.path.dirname(state_path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow)
try: os.fsync(dfd)
finally: os.close(dfd)
PY
}
logger_exit() {
  local rc=$? logger_rc=0
  trap - EXIT HUP INT TERM
  if [ "$LOGGER_ACTIVE" = 1 ]; then logger_stop || logger_rc=$?; fi
  if [ "$logger_rc" != 0 ]; then
    printf '!! STOPPED: logger exited %s; pending payload, if any, was not deleted.\n' "$logger_rc" >&8
    [ "$rc" != 0 ] || rc=4
  fi
  rm -f "$LOGGER_FIFO"
  rmdir "$LOGGER_TMP" 2>/dev/null || true
  exit "$rc"
}
trap logger_exit EXIT
trap 'exit 4' HUP INT TERM
# A durable pending transaction must be recovered before any new diagnostic is
# appended to its pinned log tail.  commit_pending starts the logger when it is
# ready either to copy a fresh payload or to resume ordinary logging.
if [ ! -e "$PENDOUT" ] && [ ! -e "$COMMIT_STATE" ]; then
  logger_start || redact_fail "cannot start coordinated logger"
fi

# Commit the actual pending bytes through the owned logger, then independently
# fsync the append target. The source file is removed only after both succeed.
commit_pending() {
  local emit_rc=0 logger_rc=0 recovery
  [ -e "$PENDOUT" ] || [ -e "$COMMIT_STATE" ] || return 0
  logger_stop || { printf '!! STOPPED: cannot pause coordinated logger for pending recovery.\n' >&8; return 1; }
  recovery="$(commit_state recover)" || return 1
  case "$recovery" in
    copied)
      fsync_log || { printf '!! STOPPED: cannot fsync copied log; durable commit state preserved.\n' >&8; return 1; }
      commit_state mark-synced || return 1
      ;;
    synced) ;;
    none|retry)
      commit_state prepare || return 1
      logger_start || { printf '!! STOPPED: cannot start coordinated logger for pending payload.\n' >&8; return 1; }
      cat "$PENDOUT" || emit_rc=$?
      logger_stop || logger_rc=$?
      if [ "$emit_rc" != 0 ] || [ "$logger_rc" != 0 ]; then
        printf '!! STOPPED: pending console payload was not durably logged (writer=%s logger=%s); buffer preserved.\n' \
          "$emit_rc" "$logger_rc" >&8
        commit_state recover >/dev/null || true
        return 1
      fi
      mark_commit_copied || { printf '!! STOPPED: cannot persist copied payload identity; recovery state preserved.\n' >&8; return 1; }
      fsync_log || { printf '!! STOPPED: cannot fsync log; copied commit state and pending buffer preserved.\n' >&8; return 1; }
      commit_state mark-synced || return 1
      ;;
    *) printf '!! STOPPED: invalid pending recovery state %s.\n' "$recovery" >&8; return 1 ;;
  esac
  if [ -e "$PENDOUT" ]; then
    rm -f "$PENDOUT" || { printf '!! STOPPED: cannot remove committed pending console buffer.\n' >&8; return 1; }
  fi
  commit_state cleanup || { printf '!! STOPPED: cannot remove durable pending commit state.\n' >&8; return 1; }
  logger_start || { printf '!! STOPPED: cannot restart coordinated logger after payload commit.\n' >&8; return 1; }
  return 0
}
# seal_run <run-dir>: redact the derived files of the run, its domain-check.txt and the buffered console output (prints nothing)
seal_run() {
  python3 "$REDACT" seal "$1" || return 1
  [ ! -e "$1/domain-check.txt" ] || python3 "$REDACT" file "$1/domain-check.txt" || return 1
  [ ! -e "$PENDOUT" ] || python3 "$REDACT" file "$PENDOUT"
}
RESUMED_PENDING=0
if [ -f "$PENDING" ]; then   # an earlier invocation stopped between run_one and the end of its redaction
  P0="$(head -n 1 "$PENDING")"
  printf '%s\n' "$P0" | grep -Eq '^P[0-9]+/r[0-9]+(\.retry[0-9]+)?$' || redact_fail "unreadable $PENDING"
  echo "== resume: $P0 was interrupted before its redaction finished; redacting it again before anything else"
  seal_run "$OUT/$P0" || redact_fail "$P0"
  RESUMED_PENDING=1
fi
if [ -e "$PENDOUT" ] || [ -e "$COMMIT_STATE" ]; then
  [ ! -e "$PENDOUT" ] || python3 "$REDACT" file "$PENDOUT" || redact_fail "$PENDOUT"
  echo "== resume: console output of the interrupted run (redacted):"
  commit_pending || redact_fail "$PENDOUT logger commit"
fi
if [ "$RESUMED_PENDING" = 1 ]; then rm -f "$PENDING" || redact_fail "cannot remove $PENDING"; fi
echo "== $(utc) batch model=$MODEL plugin=${PLUGIN_REF:-WORKTREE}@${PLUGIN_SHA:0:7} repeats=$REPEATS ids: $IDS"

K=1; STOP=""; CRASH_STREAK=0
while [ "$K" -le "$REPEATS" ] && [ -z "$STOP" ]; do
  for ID in $IDS; do
    SLOT="$OUT/$ID/r$K"; DONE=""; CRASHES=0; TARGET=""; N=0
    while [ "$N" -le 50 ]; do
      if [ "$N" = 0 ]; then CAND="$SLOT"; else CAND="$SLOT.retry$N"; fi
      case "$(run_state "$CAND")" in
        complete) DONE="$CAND"; break ;;
        absent) TARGET="$CAND"; break ;;
        incomplete) CRASHES=$((CRASHES + 1)) ;;
        infra:*) ;;   # kept, not scored, does not count against MAX_RETRY
      esac
      N=$((N + 1))
    done
    if [ -n "$DONE" ]; then echo "-- skip $ID r$K (complete: $DONE)"; continue; fi
    if [ -z "$TARGET" ] || [ "$CRASHES" -gt "$MAX_RETRY" ]; then echo "-- $ID r$K: crashed $CRASHES time(s), retries exhausted; left as is"; continue; fi
    mkdir -p "$OUT/$ID"
    printf '%s\n' "$ID/$(basename "$TARGET")" > "$PENDING.tmp" && mv -f "$PENDING.tmp" "$PENDING" || redact_fail "cannot write $PENDING"
    # run_one starts a watchdog sleep. Pause the logger first so that child
    # cannot inherit the FIFO writer and keep the awaited logger alive.
    logger_stop || redact_fail "logger before $ID/$(basename "$TARGET")"
    # A subshell closes the saved console descriptors before run_one creates
    # its watchdog, so no descendant can keep either capture sink open.
    ( exec 7>&- 8>&-; run_one "$ID" "$MODEL" "$TARGET" ) > "$PENDOUT" 2>&1 || true
    logger_start || redact_fail "logger after $ID/$(basename "$TARGET")"
    if [ -f "$TARGET/run.jsonl" ] && [ -n "$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(next((s.get("domain_4_0_1","") for s in d["scenarios"] if s["id"]==sys.argv[2]),""))' "$SCENARIOS" "$ID")" ]; then
      python3 "$BATTERY_DIR/check-domain.py" "$ID" "$TARGET/run.jsonl" > "$TARGET/domain-check.txt" 2>&1; echo "exit=$?" >> "$TARGET/domain-check.txt"
    fi
    python3 - "$TARGET/meta.json" <<'PY' || redact_fail "$TARGET/meta.json battery identity"
import json, os, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
data["battery"] = "4.0.2"
tmp = path + ".battery.tmp"
with open(tmp, "x", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, sort_keys=True)
    fh.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY
    seal_run "$TARGET" || redact_fail "$TARGET"
    commit_pending || redact_fail "$PENDOUT logger commit"
    rm -f "$PENDING" || redact_fail "cannot remove $PENDING"
    case "$(run_state "$TARGET")" in
      infra:*) STOP="INFRA error at $ID r$K ($(run_state "$TARGET"); see $TARGET/run.stderr and the result event). This is rate limit / credits / execution failure, not behaviour: the run is kept, not scored, and the slot will be re-run. Wait for the limit to reset, then re-invoke the SAME command."; break ;;
      incomplete|absent) CRASH_STREAK=$((CRASH_STREAK + 1))
        if [ "$CRASH_STREAK" -ge 3 ]; then STOP="3 runs in a row ended without a result event (last: $TARGET). Check claude login/network, then re-invoke the SAME command."; break; fi ;;
      complete) CRASH_STREAK=0 ;;
    esac
  done
  K=$((K + 1))
done

python3 "$REPO/eval/probe-agg.py" "$OUT"
python3 "$REDACT" file "$OUT/SUMMARY.tsv" && python3 "$REDACT" file "$OUT/AGG.tsv" || redact_fail "SUMMARY.tsv / AGG.tsv"
echo "--- AGG.tsv ($OUT)"; cat "$OUT/AGG.tsv"
MISSING="$(python3 - "$OUT" "$REPEATS" $IDS <<'PY'
import csv, sys
out, repeats, ids = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
rows = list(csv.DictReader(open(out + "/SUMMARY.tsv", encoding="utf-8"), delimiter="\t"))
ok = {(r["id"], r["run"].split(".")[0]) for r in rows if r["exit"] in ("0", "1")}
print(sum(1 for i in ids for k in range(1, repeats + 1) if (i, f"r{k}") not in ok))
PY
)"
if [ -n "$STOP" ]; then echo "!! BATCH STOPPED: $STOP"; echo "SUMMARY battery-4.0.2 STOPPED slots_without_scored_run=$MISSING dir=$OUT"; exit 5; fi
echo "SUMMARY battery-4.0.2 model=$MODEL plugin=${PLUGIN_REF:-WORKTREE}@${PLUGIN_SHA:0:7} slots=$(( $(echo $IDS | wc -w) * REPEATS )) slots_without_scored_run=$MISSING dir=$OUT"
[ "$MISSING" = 0 ] || exit 2
exit 0
