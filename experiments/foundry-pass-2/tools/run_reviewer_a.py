"""Reviewer A runner. Run from experiments/foundry-pass-2:

    python3 tools/run_reviewer_a.py identity      bind identity record + probes
    python3 tools/run_reviewer_a.py review [N]    review next N unreviewed shards
    python3 tools/run_reviewer_a.py status
    python3 tools/run_reviewer_a.py qualify       bounded public-only instrument
                                                  qualification (18197913 /
                                                  18197956): public fixture,
                                                  synthetic probes, no private
                                                  mount, out-qualification/,
                                                  identity ineligible for binding

Identity is bound (and leak probes pass) BEFORE the first real review; the
identity digest is part of every task prompt, so a review can never run
against an unbound identity. Outputs: out/reviewer-a/.
"""

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS2 = os.path.dirname(HERE)
sys.path.insert(0, PASS2)

from engine import canon, reviewer  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(PASS2, "..", ".."))
ARI = os.path.join(PASS2, "evaluator", "ari")
OUT = os.path.join(PASS2, "out")
A_OUT = os.path.join(OUT, "reviewer-a")
MODEL = os.environ.get("FOUNDRY_REVIEWER_A_MODEL", "claude-sonnet-5")
FORBIDDEN_TARGET = os.path.join(REPO_ROOT, "README.md")
OUTPUT_SCHEMA = os.path.join(ARI, "reviewer-output-v0.1.schema.json")
FIXTURE_OUT = os.path.join(PASS2, "out-fixture")
Q_OUT = os.path.join(PASS2, "out-qualification", "reviewer-a")
# A qualification ruling authorizes ONE CLI invocation (18218358: "any
# invocation that reaches a model spends this one qualification authority.
# No retry, second invocation ... is authorized"). The governed-review path
# keeps IsolatedSession's default retry policy; the qualify path may not
# retry at all (Ari, 18321030, blocking finding 1: counting is not
# enforcement).
QUALIFY_ATTEMPTS = 1
RESERVATIONS_DIR = "reservations"


def _sha(path):
    return canon.file_sha256(path)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def bundle_digests(out_root=None):
    bundle_path = os.path.join(out_root or OUT, "review-input-bundle.json")
    bundle = canon.load_json(bundle_path)
    return {
        "CONTRACT_SHA256": bundle["bindings"]["reviewer_contract"]["sha256"],
        "REVIEW_INPUT_BUNDLE_SHA256": _sha(bundle_path),
        "SHARD_MANIFEST_SHA256": bundle["shard_manifest"]["sha256"],
    }


def load_template(out_root=None):
    """The ratified schema-bearing task template the reviewer will SEE,
    verified against the digest the bundle-bound reviewer contract binds
    (`prompts.task_template.sha256`) before any prompt is rendered."""
    bundle = canon.load_json(os.path.join(out_root or OUT,
                                          "review-input-bundle.json"))
    contract_binding = bundle["bindings"]["reviewer_contract"]
    contract_path = os.path.join(ARI, os.path.basename(contract_binding["path"]))
    if _sha(contract_path) != contract_binding["sha256"]:
        raise SystemExit("reviewer contract bytes do not match the bundle "
                         "binding; refusing to load the task template")
    contract = canon.load_json(contract_path)
    bound = contract["prompts"]["task_template"]
    return reviewer.load_task_template(
        os.path.join(ARI, os.path.basename(bound["path"])), bound["sha256"])


def load_schema(out_root=None):
    """The output schema the reviewer will SEE, verified before any prompt
    is rendered (18197913, item 2) against the digest the isolated-reviewer
    CONTRACT binds (`output_schema.sha256`), the contract itself being the
    one the bundle binds; and, when the bundle also binds the schema
    directly, against that digest too."""
    bundle = canon.load_json(os.path.join(out_root or OUT,
                                          "review-input-bundle.json"))
    contract_binding = bundle["bindings"]["reviewer_contract"]
    contract_path = os.path.join(ARI, os.path.basename(contract_binding["path"]))
    if _sha(contract_path) != contract_binding["sha256"]:
        raise SystemExit("reviewer contract bytes do not match the bundle "
                         "binding; refusing to load the output schema")
    contract = canon.load_json(contract_path)
    bound = contract["output_schema"]["sha256"]
    direct = bundle["bindings"].get("reviewer_output_schema", {}).get("sha256")
    if direct is not None and direct != bound:
        raise SystemExit("bundle and contract bind different output schema "
                         "digests")
    return reviewer.load_output_schema(OUTPUT_SCHEMA, bound)


def schema_validator(output):
    """Ari's validator, run as delivered (node + ajv from the repo)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(output, f)
        path = f.name
    try:
        proc = subprocess.run(
            ["node", os.path.join(ARI, "validate-reviewer-output-v0.1.mjs"),
             os.path.join(ARI, "reviewer-output-v0.1.schema.json"), path],
            capture_output=True, text=True,
            env={**os.environ, "DWTC_REPO_ROOT": REPO_ROOT})
    finally:
        os.unlink(path)
    return proc.returncode == 0, {
        "validator_sha256": _sha(os.path.join(
            ARI, "validate-reviewer-output-v0.1.mjs")),
        "returncode": proc.returncode,
        "stderr_head": proc.stderr[:2000],
    }


def make_session(system_prompt, cwd, attempts=3):
    return reviewer.IsolatedSession(MODEL, system_prompt, cwd, attempts=attempts)


def cli_version():
    proc = subprocess.run(["claude", "--version"], capture_output=True,
                          text=True)
    return proc.stdout.strip() or proc.stderr.strip()


def bind_identity():
    os.makedirs(A_OUT, exist_ok=True)
    system_prompt = _read(os.path.join(ARI, "reviewer-system-prompt-v0.1.md"))
    template = load_template()
    digests = bundle_digests()
    schema = load_schema()
    cwd = tempfile.mkdtemp(prefix="foundry-reviewer-a-")
    session = make_session(system_prompt, cwd)
    # Probes run with a provisional identity digest (all zeros): the probe
    # prompts are not reviews, and the bound identity includes the probe
    # transcript digest, so it cannot exist before the probes do.
    probe_digests = dict(digests, REVIEWER_IDENTITY_SHA256="0" * 64)
    # Evidence-first: the harness writes every raw prompt and response to
    # this path as it happens, and the complete failed-preflight record
    # before any exception reaches us (discussioncomment-18197092). On
    # failure the exception propagates and no identity is bound; the
    # evidence stays on disk. Every outcome also gets a content-addressed
    # sibling (-FAILED- or -PASSED-) that no later attempt can rewrite.
    transcript_path = os.path.join(A_OUT, "leak-probe-transcript.json")
    records, transcripts = reviewer.run_leak_probes(
        session, template, probe_digests, cwd, FORBIDDEN_TARGET,
        evidence_path=transcript_path, schema=schema,
        schema_validator=schema_validator)
    persisted = canon.load_json(transcript_path)
    if persisted.get("preflight_result") != "PASS":
        raise SystemExit("refusing to bind identity: persisted preflight "
                         f"result is {persisted.get('preflight_result')!r}")
    transcript_sha = _sha(transcript_path)
    boundary = session.environment_boundary()
    configuration = {"command": session.command()[:-1] + ["<system prompt>"],
                     "timeout_s": session.timeout, "attempts": session.attempts}
    harness_sha = _sha(os.path.join(PASS2, "engine", "reviewer.py"))
    identity = {
        "artifact_version": "foundry-pass-2-reviewer-identity/experimental-v0.1",
        "reviewer_role": "reviewer_a",
        "operator_lineage": "CC (Claude Code harness); fresh headless role "
                            "sessions, not the interactive or builder session",
        "model_provider": "Anthropic",
        "model_id": MODEL,
        "model_version_or_build": cli_version(),
        "system_prompt_sha256": _sha(os.path.join(
            ARI, "reviewer-system-prompt-v0.1.md")),
        "task_prompt_template_sha256": _sha(os.path.join(
            ARI, "reviewer-task-template-v0.1.md")),
        "output_schema_sha256": schema["sha256"],
        "output_schema_model_visible": True,
        "harness_sha256": harness_sha,
        "parser_sha256": harness_sha,
        "tool_allowlist_sha256": canon.content_digest([]),
        "settings_sources_sha256": canon.content_digest(""),
        "configuration_sha256": canon.content_digest(configuration),
        "environment_boundary_sha256": canon.content_digest(boundary),
        "leak_probe_transcript_sha256": transcript_sha,
        "session_ids_sha256": canon.content_digest(
            [t["result"].get("session_id") for t in transcripts]),
        "bound_before_first_real_review": True,
        "bindings": digests,
        "configuration": configuration,
        "environment_boundary": boundary,
        "leak_probes": records,
    }
    identity_sha = canon.write_canonical(
        os.path.join(A_OUT, "reviewer-identity.json"), identity)
    write_run_record_manifest()
    print(json.dumps(records, indent=1))
    print("REVIEWER_IDENTITY_SHA256:", identity_sha)


def select_pending(manifest, records_dir, count):
    done = {n.replace(".json", "") for n in os.listdir(records_dir)}
    pending = [m for m in manifest["shards"] if m["shard_id"] not in done]
    return pending[:count]


def preverify_selection(selected, out_root):
    """Ari exact-diff review of 7b6d454 (discussioncomment-18206472): every
    selected shard is digest-checked against the manifest AND has every
    record's identity recomputed (reviewer.verify_shard_records) BEFORE any
    reviewer session is constructed or any model call is made. A failure on
    any shard aborts the whole review command; it is never swallowed into
    the per-shard continuation path. Returns {shard_id: verification list}."""
    verified = {}
    for member in selected:
        shard_path = os.path.join(out_root, member["path"])
        if _sha(shard_path) != member["sha256"]:
            raise SystemExit(f"review aborted before any session: shard "
                             f"digest drift: {member['shard_id']}")
        shard = canon.load_json(shard_path)
        try:
            verified[member["shard_id"]] = reviewer.verify_shard_records(shard)
        except reviewer.ReviewerError as err:
            raise SystemExit(f"review aborted before any session: "
                             f"{str(err)[:600]}")
    return verified


def review(count, session_factory=None, out_root=None, a_out=None):
    out_root = out_root or OUT
    a_out = a_out or A_OUT
    session_factory = session_factory or make_session
    identity_path = os.path.join(a_out, "reviewer-identity.json")
    if not os.path.isfile(identity_path):
        raise SystemExit("identity not bound; run `identity` first")
    digests = dict(bundle_digests(out_root),
                   REVIEWER_IDENTITY_SHA256=_sha(identity_path))
    identity = canon.load_json(identity_path)
    if identity.get("eligible_for_binding") is False or identity.get(
            "qualification_only"):
        raise SystemExit("identity is a qualification identity, ineligible "
                         "for review")
    if identity["bindings"] != {k: digests[k] for k in identity["bindings"]}:
        raise SystemExit("bundle changed since identity was bound; rebind")
    schema = load_schema(out_root)
    if schema["sha256"] != identity["output_schema_sha256"]:
        raise SystemExit("output schema changed since identity was bound")
    system_prompt = _read(os.path.join(ARI, "reviewer-system-prompt-v0.1.md"))
    template = load_template(out_root)
    manifest = canon.load_json(os.path.join(out_root, "shard-manifest.json"))
    outputs_dir = os.path.join(a_out, "outputs")
    records_dir = os.path.join(a_out, "run-records")
    os.makedirs(outputs_dir, exist_ok=True)
    os.makedirs(records_dir, exist_ok=True)
    selected = select_pending(manifest, records_dir, count)
    # hard stop for the WHOLE selection before any session exists
    preverify_selection(selected, out_root)
    cwd = tempfile.mkdtemp(prefix="foundry-reviewer-a-")
    for member in selected:
        shard_path = os.path.join(out_root, member["path"])
        session = session_factory(system_prompt, cwd)
        try:
            record = reviewer.review_shard(
                session, template, digests, shard_path,
                member["artifact_ids"], schema_validator, schema)
        except reviewer.ReviewerError as err:
            record = {"shard_id": member["shard_id"],
                      "verdict": "review-execution-failure",
                      "problems": [str(err)[:500]]}
        canon.write_canonical(
            os.path.join(records_dir, member["shard_id"] + ".json"), record)
        if record["verdict"] == "fixed":
            canon.write_canonical(
                os.path.join(outputs_dir, member["shard_id"] + ".json"),
                record["output"])
        counts = {}
        for d in record.get("output", {}).get("dispositions", []):
            counts[d["verdict"]] = counts.get(d["verdict"], 0) + 1
        print(member["shard_id"], record["verdict"], json.dumps(counts),
              record.get("problems", []), flush=True)
    write_run_record_manifest(a_out)


def refuse_if_ledgered(ledger_path, head):
    """One qualification attempt per exact commit (18197956 item 2;
    18206224 item 4): if the preserved local ledger already records this
    head, refuse BEFORE any session is created or model call made."""
    if not os.path.isfile(ledger_path):
        return
    prior = [a for a in canon.load_json(ledger_path)["attempts"]
             if a.get("head") == head]
    if prior:
        raise SystemExit(
            f"qualification refused: head {head} already has "
            f"{len(prior)} ledgered attempt(s) ({prior[0]['result']}, "
            f"attempt {prior[0]['attempt_id']}); a new attempt needs a new "
            f"exact commit")


def reservation_path(q_out, head):
    if not valid_head(head):
        raise SystemExit(f"qualification refused: {head[:60]!r} is not a "
                         "40-hex commit sha (adversary F3: a non-sha head "
                         "could name a path outside the qualification root)")
    return os.path.join(q_out, RESERVATIONS_DIR, f"{head}.json")


def spent_head_reasons(q_out, head):
    """Every durable trace that this exact head has already been given to
    qualify(), in authority order: (1) the pre-call reservation, (2) any
    immutable attempt record, (3) the ledger projection. Any one of them
    is sufficient to refuse. The ledger alone was the sole refusal source
    before this (Ari, 18321030, blocking finding 2): a failed ledger write
    after the model call left the head absent from the only place refusal
    looked, and a second call spent a second invocation."""
    reasons = []
    res = reservation_path(q_out, head)
    if os.path.lexists(res):
        # any object at the reservation path spends the head; a regular
        # file is read without following links, anything else is reported
        try:
            meta = canon.load_json_regular(res)
            when = meta.get("reserved_utc", "?")
        except Exception as err:  # noqa: BLE001 - unreadable is still spent
            when = f"unreadable ({type(err).__name__})"
        reasons.append(f"reservation {os.path.relpath(res, q_out)} "
                       f"(reserved {when})")
    records = []
    if os.path.isdir(q_out):
        for name in sorted(os.listdir(q_out)):
            if name.startswith("qualification-attempt-") and name.endswith(".json"):
                try:
                    rec = canon.load_json_regular(os.path.join(q_out, name))
                except Exception:  # noqa: BLE001 - unreadable records still count
                    rec = {"head": None}
                if rec.get("head") == head or rec.get("head") is None:
                    records.append((name, rec.get("result", "unknown")))
    if records:
        reasons.append(f"{len(records)} attempt record(s) ("
                       + ", ".join(f"{n} {r}" for n, r in records) + ")")
    ledger = os.path.join(q_out, "qualification-ledger.json")
    if os.path.lexists(ledger) and not canon.is_regular(ledger):
        # a directory, a symlink (18321488 finding 2), a socket: none can
        # prove the head unspent, and a symlink is never read through
        reasons.append("ledger path exists but is not a regular file; the "
                       "ledger cannot prove this head unspent")
    elif canon.is_regular(ledger):
        try:
            prior = [a for a in canon.load_json_regular(ledger)["attempts"]
                     if a.get("head") == head]
        except Exception as err:  # noqa: BLE001 - adversary F7: report, not trace
            prior = []
            reasons.append(f"ledger unreadable ({type(err).__name__}: "
                           f"{str(err)[:120]}); the ledger cannot prove this "
                           "head unspent")
        if prior:
            reasons.append(f"already has {len(prior)} ledgered attempt(s) "
                           f"({prior[0]['result']}, attempt "
                           f"{prior[0]['attempt_id']})")
    return reasons


def refuse_if_spent(q_out, head):
    """One qualification attempt per exact commit, enforced against every
    durable trace, BEFORE any session is created or model call made."""
    reasons = spent_head_reasons(q_out, head)
    if reasons:
        raise SystemExit(
            f"qualification refused: head {head} is spent: "
            + "; ".join(reasons) + "; a new attempt needs a new exact commit")


def reserve_head(q_out, head, meta):
    """Exclusive, durable reservation of this exact head, written after
    every deterministic input check has passed and BEFORE any session
    exists. Exclusive create (O_EXCL) makes two concurrent calls resolve
    to exactly one holder; fsync on the file and its directory makes the
    reservation survive a crash before any later write. The reservation
    is authoritative for refusal even if the attempt record or the ledger
    is never written: a reserved head with no attempt record is a spent
    head by design (it may have reached the model), and needs a new
    commit. Never modified after creation."""
    path = reservation_path(q_out, head)
    try:
        canon.refuse_unless_real_dir(os.path.dirname(path), "reservations directory")
    except canon.PathBoundaryError as err:
        raise SystemExit(f"qualification refused: {err}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = dict(meta, artifact_version=
                  "foundry-pass-2-qualification-reservation/experimental-v0.1",
                  head=head)
    data = canon.canonical_bytes(record)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise SystemExit(
            f"qualification refused: head {head} is already reserved "
            f"({os.path.relpath(path, q_out)}); a new attempt needs a new "
            "exact commit")
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    dfd = os.open(os.path.dirname(path), os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return path


def write_attempt_record(q_out, record):
    """Immutable, content-addressed attempt record. Separate seam so a
    write failure here can be injected by tests (18321030 finding 2)."""
    data = canon.canonical_bytes(record)
    rec_sha = canon.bytes_digest(data)
    rec_path = os.path.join(q_out, f"qualification-attempt-{rec_sha}.json")
    with open(rec_path, "xb") as f:
        f.write(data)
    return rec_sha, rec_path


def append_ledger(q_out, entry):
    """Ledger projection of the attempt records. Separate seam so a write
    failure here can be injected by tests (18321030 finding 2). The ledger
    is a convenience view; refusal never depends on it alone."""
    ledger = os.path.join(q_out, "qualification-ledger.json")
    # lstat-gated read, no-follow; then a same-directory temporary regular
    # file, fsync, atomic replace (18321488 finding 2: open(..., 'wb') on a
    # symlinked ledger overwrote its external target)
    canon.refuse_unless_regular(ledger, "ledger")
    entries = (canon.load_json_regular(ledger)["attempts"]
               if canon.is_regular(ledger) else [])
    entries.append(entry)
    canon.write_canonical_atomic(ledger, {
        "artifact_version": "foundry-pass-2-qualification-ledger/experimental-v0.1",
        "attempts": entries})
    return ledger


def check_evidence_paths(q_out, root=None):
    """Path-boundary gate for the mutable evidence root, run BEFORE any
    reservation is written and before any pre-existing evidence is read
    (18321488 blocking finding 2; authorized by 18321531). The evidence
    directories are untracked, so a git-clean tree says nothing about
    what sits in them. With lstat, never following links:

    - q_out and every ancestor below the pass root must be real
      directories (or absent);
    - every entry directly inside q_out must be a regular file, except the
      reservations directory, which must be a real directory whose
      entries are all regular files.

    Returns the list of violations (empty when clean); the caller refuses
    on any. Nothing is opened, so a planted link's target is never read."""
    root = PASS2 if root is None else root
    problems = []

    def describe(path):
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(st.st_mode):
            return "symlink"
        if stat.S_ISDIR(st.st_mode):
            return "directory"
        if stat.S_ISREG(st.st_mode):
            return "regular file"
        return "special file"

    # ancestors between the pass root and q_out, then q_out itself
    chain = []
    cur = os.path.abspath(q_out)
    root_abs = os.path.abspath(root)
    while True:
        chain.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur or parent == root_abs or not cur.startswith(root_abs + os.sep):
            break
        cur = parent
    for path in reversed(chain):
        kind = describe(path)
        if kind not in (None, "directory"):
            problems.append(f"{os.path.relpath(path, root_abs) if path.startswith(root_abs) else path} is a {kind}, not a directory")
    if problems or describe(os.path.abspath(q_out)) is None:
        return problems
    for name in sorted(os.listdir(q_out)):
        path = os.path.join(q_out, name)
        kind = describe(path)
        if name == RESERVATIONS_DIR:
            if kind != "directory":
                problems.append(f"{name} is a {kind}, not a directory")
                continue
            for sub in sorted(os.listdir(path)):
                skind = describe(os.path.join(path, sub))
                if skind != "regular file":
                    problems.append(f"{name}/{sub} is a {skind}, not a regular file")
        elif kind != "regular file":
            problems.append(f"{name} is a {kind}, not a regular file")
    return problems


HEAD_RE = re.compile(r"[0-9a-f]{40}")


def valid_head(head):
    """A head is exactly one lowercase 40-hex commit sha. Anything else
    (empty string from a failed git, the literal HEAD of an empty repo, a
    path fragment) is refused before it can name a ledger line or be
    interpolated into a reservation path (adversary F2, F3)."""
    return isinstance(head, str) and HEAD_RE.fullmatch(head) is not None


def git_head():
    """Exact commit sha and clean-tree flag, or a hard stop. A git failure
    used to read as head '' with a clean tree (adversary F2: two model
    calls spent at no head, ledger line naming no head)."""
    rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True, cwd=PASS2)
    status = subprocess.run(["git", "status", "--porcelain",
                             "--untracked-files=no"], capture_output=True,
                            text=True, cwd=PASS2)
    if rev.returncode != 0 or status.returncode != 0:
        raise SystemExit("qualification refused: git could not report the "
                         f"head (rev-parse rc={rev.returncode} "
                         f"{rev.stderr.strip()[:200]!r}; status "
                         f"rc={status.returncode} {status.stderr.strip()[:200]!r})")
    head = rev.stdout.strip()
    if not valid_head(head):
        raise SystemExit("qualification refused: git reported "
                         f"{head[:60]!r}, not a 40-hex commit sha")
    return head, status.stdout.strip() == ""


STALE_MANIFEST = "stale-transcript-manifest.json"


def _fsync_path(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stash_stale_transcript(q_out, head):
    """The working transcript file has a fixed name; a copy left by a prior
    attempt made a later zero-call abort look like a spent attempt and
    ledgered the prior attempt's evidence under the new head (adversary
    F4). Before any session exists, any working file present is moved
    aside to a content-addressed STALE sibling (never deleted), so that
    after the run the working file exists only if THIS run wrote it.

    The sibling's bytes are compared, never assumed, when a file of that
    name already exists (adversary N5: a planted collision let the
    working file be unlinked while the sibling held other bytes), the
    sibling is fsynced before the working file is removed, and a manifest
    records what the stashed transcript said about itself (attempt_id,
    started_utc, preflight_result, how many model calls it recorded) and
    which heads were reserved at the time, so a zero-call crash at an
    earlier head keeps its proof (adversary N4)."""
    working = os.path.join(q_out, "leak-probe-transcript.json")
    # a symlink at the working path is refused by check_evidence_paths
    # before this runs; here it is never read through (18321488 finding 2)
    canon.refuse_unless_regular(working, "working transcript")
    if not canon.is_regular(working):
        return None
    data = canon.read_regular_bytes(working)
    digest = canon.bytes_digest(data)
    stale = os.path.join(q_out, f"leak-probe-transcript-STALE-{digest}.json")
    n = 0
    while True:
        try:
            with open(stale, "xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            break
        except FileExistsError:
            existing = canon.read_regular_bytes(stale)
            if existing == data:
                break  # the same bytes are already preserved under this name
            n += 1
            stale = os.path.join(
                q_out, f"leak-probe-transcript-STALE-{digest}-{n}.json")
    _fsync_path(q_out)
    try:
        meta = json.loads(data.decode("utf-8"))
    except Exception:  # noqa: BLE001 - unreadable stale bytes are still kept
        meta = {}
    transcripts = meta.get("transcripts") if isinstance(meta, dict) else None
    calls = (sum(1 for t in transcripts if isinstance(t, dict)
                 and t.get("result") is not None)
             if isinstance(transcripts, list) else None)
    res_dir = os.path.join(q_out, RESERVATIONS_DIR)
    reserved = sorted(f[:-5] for f in os.listdir(res_dir)
                      if f.endswith(".json")) if os.path.isdir(res_dir) else []
    entry = {
        "stale_path": os.path.relpath(stale, q_out), "sha256": digest,
        "byte_length": len(data),
        "attempt_id": meta.get("attempt_id") if isinstance(meta, dict) else None,
        "started_utc": meta.get("started_utc") if isinstance(meta, dict) else None,
        "preflight_result": (meta.get("preflight_result")
                             if isinstance(meta, dict) else None),
        "model_calls_recorded": calls,
        "stashed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stashed_before_attempt_at_head": head,
        "heads_reserved_at_stash_time": reserved,
    }
    manifest_path = os.path.join(q_out, STALE_MANIFEST)
    manifest = {"artifact_version":
                "foundry-pass-2-stale-transcript-manifest/experimental-v0.1",
                "members": []}
    canon.refuse_unless_regular(manifest_path, "stale-transcript manifest")
    if canon.is_regular(manifest_path):
        try:
            manifest = canon.load_json_regular(manifest_path)
        except Exception:  # noqa: BLE001 - never lose the stash over bookkeeping
            manifest = {"artifact_version": manifest["artifact_version"],
                        "members": [], "note": "prior manifest unreadable"}
    manifest["members"].append(entry)
    canon.write_canonical_atomic(manifest_path, manifest)
    os.unlink(working)
    _fsync_path(q_out)
    return stale


def known_attempt_ids(q_out):
    """Every attempt_id already recorded under q_out (attempt records and
    ledger). Evidence produced by this run must carry a NEW id."""
    ids = set()
    if os.path.isdir(q_out):
        for name in os.listdir(q_out):
            if name.startswith("qualification-attempt-") and name.endswith(".json"):
                try:
                    ids.add(canon.load_json_regular(
                        os.path.join(q_out, name)).get("attempt_id"))
                except Exception:  # noqa: BLE001
                    pass
    ledger = os.path.join(q_out, "qualification-ledger.json")
    if canon.is_regular(ledger):
        try:
            for a in canon.load_json_regular(ledger)["attempts"]:
                ids.add(a.get("attempt_id"))
        except Exception:  # noqa: BLE001
            pass
    ids.discard(None)
    return ids


def qualify():
    """Bounded public-only instrument qualification (18197913, adopted by
    maintainer ruling 18197956). Reads ONLY the public fixture root; the
    private bundle is never opened. Writes ONLY under out-qualification/.
    Produces a qualification identity marked ineligible for binding and a
    ledger line for the board. One attempt per exact commit is the rule;
    this tool records the head and refuses a dirty tree so the ledger line
    names bytes that exist."""
    if not os.path.isfile(os.path.join(FIXTURE_OUT, "review-input-bundle.json")):
        raise SystemExit("public fixture missing; run tools/emit_test_fixture.py")
    head, clean = git_head()
    if not valid_head(head):
        raise SystemExit(f"qualification refused: {str(head)[:60]!r} is not "
                         "a 40-hex commit sha")
    if not clean:
        raise SystemExit("qualification refused: working tree is not clean "
                         f"at {head}")
    # the ruling names a model ID; the operator states it from the ruling
    # and it is checked against the harness's model BEFORE anything is
    # spent, then recorded in the reservation, record, and ledger (adversary
    # F6: an env override was accepted and ledgered silently). This is an
    # attestation, not enforcement (adversary N1): the harness cannot read
    # the ruling, so two matching operator strings satisfy it; the receipt
    # makes the claim checkable, it does not make it true.
    ruled_model = os.environ.get("FOUNDRY_QUALIFY_RULED_MODEL", "")
    if not ruled_model:
        raise SystemExit("qualification refused: FOUNDRY_QUALIFY_RULED_MODEL "
                         "is not set; state the model ID the ruling names")
    if ruled_model != MODEL:
        raise SystemExit("qualification refused: the ruling names model "
                         f"{ruled_model!r} but the harness would run "
                         f"{MODEL!r}")
    # path-boundary gate BEFORE anything under the evidence root is read
    # or created (18321488 finding 2): the root, its ancestors, the
    # reservations directory, and every pre-existing evidence file are
    # inspected with lstat; symlinks and unexpected types are a refusal
    problems = check_evidence_paths(Q_OUT)
    if problems:
        raise SystemExit("qualification refused: evidence path boundary: "
                         + "; ".join(problems))
    os.makedirs(Q_OUT, exist_ok=True)
    refuse_if_spent(Q_OUT, head)
    # input identities are read BEFORE the attempt: anything that can fail
    # here fails with nothing spent (CI on c0b7deb: cli_version() ran after
    # the attempt and its failure would have lost the ledger line)
    cli_build = cli_version()
    system_prompt = _read(os.path.join(ARI, "reviewer-system-prompt-v0.1.md"))
    template = load_template(FIXTURE_OUT)
    digests = bundle_digests(FIXTURE_OUT)
    schema = load_schema(FIXTURE_OUT)
    # every deterministic check has passed; from here the head is spent
    # whatever happens next (reservation is authoritative for refusal even
    # if no later write succeeds)
    reservation = reserve_head(Q_OUT, head, {
        "reserved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_id": MODEL, "ruled_model_id": ruled_model,
        "model_version_or_build": cli_build,
        "fixture_bindings": digests, "attempts_allowed": QUALIFY_ATTEMPTS})
    # a working transcript left by a prior attempt must not be mistaken for
    # this run's evidence (adversary F4); ids already recorded must not
    # reappear as this run's attempt
    stale = stash_stale_transcript(Q_OUT, head)
    prior_ids = known_attempt_ids(Q_OUT)
    cwd = tempfile.mkdtemp(prefix="foundry-qualify-a-")
    try:
        session = make_session(system_prompt, cwd, QUALIFY_ATTEMPTS)
    except BaseException as err:  # noqa: B036 - zero-call, reported as such
        raise SystemExit("qualification did not start an attempt: session "
                         f"construction failed: {type(err).__name__}: "
                         f"{str(err)[:300]} (head stays reserved)")
    # the session must SAY what it allows; a session that does not expose
    # its retry policy cannot be trusted to have one (adversary F5)
    if getattr(session, "attempts", None) != QUALIFY_ATTEMPTS:
        raise SystemExit("qualification refused before any call: session "
                         f"reports attempts={getattr(session, 'attempts', None)!r}; "
                         f"the ruling allows exactly {QUALIFY_ATTEMPTS}")
    probe_digests = dict(digests, REVIEWER_IDENTITY_SHA256="0" * 64)
    transcript_path = os.path.join(Q_OUT, "leak-probe-transcript.json")
    result = "PASS"
    error = None
    try:
        reviewer.run_leak_probes(
            session, template, probe_digests, cwd, FORBIDDEN_TARGET,
            evidence_path=transcript_path, schema=schema,
            schema_validator=schema_validator)
    except reviewer.ReviewerError as err:
        result = "FAIL"
        error = str(err)[:500]
    except BaseException as err:  # noqa: B036 - a spent attempt is ledgered
        # Defense in depth behind the harness's own conversion: nothing
        # that happens after the attempt started may leave the head
        # un-ledgered (self-adversarial pass on 89a56c9, hole 2).
        result = "FAIL"
        error = f"harness aborted: {type(err).__name__}: {str(err)[:400]}"
    # the live session's own count of the last logical call, read from the
    # object in hand rather than from disk (isolated adversary, second pass
    # on this correction, F1: the handler that copies the live count into
    # the transcript can itself be interrupted, or both of its persists can
    # fail, leaving the on-disk entry at zero while the session still holds
    # the count; a receipt must never be lower than what the session says)
    live = getattr(session, "last_invocations", None)
    live = live if isinstance(live, int) else None
    # the cumulative total, when the session keeps one, is the floor for
    # every count published below: the per-call value passes through zero
    # at the top of each call, so a second-probe interrupt in that window
    # read as "nothing started" after the first probe had spent a call
    # (second adversary pass on 18321531, N1)
    total = getattr(session, "total_invocations", None)
    total = total if isinstance(total, int) else None
    started = total if total is not None else live
    if not canon.is_regular(transcript_path):
        if started:
            live = started
            # a call started (the session says so) and its evidence did not
            # survive: this is NOT a zero-call exit; the head stays reserved
            raise SystemExit("qualification attempt left no evidence on "
                             f"disk but the session reports {live} CLI "
                             "invocation(s) started; treat the head as "
                             f"spent (it stays reserved): {error}")
        # nothing was persisted and the session reports nothing started, so
        # no model call was made; the head has not spent its attempt
        raise SystemExit("qualification did not start an attempt: "
                         f"{error or 'no evidence written'}")
    persisted = canon.load_json_regular(transcript_path)
    if persisted.get("attempt_id") in prior_ids:
        raise SystemExit("qualification evidence carries a previously "
                         f"recorded attempt_id {persisted.get('attempt_id')}; "
                         "this run produced no evidence of its own")
    calls = sum(1 for t in persisted["transcripts"] if t["result"] is not None)
    reconciliation = None
    if hasattr(session, "last_invocations"):
        invocations = sum(t.get("cli_invocations", 1 if t["result"] is not None
                                else 0) for t in persisted["transcripts"])
        accounting = "session-reported"
        entries = persisted["transcripts"]
        # per-entry fallback for sessions without a cumulative total; with
        # a total the per-call counter is not consulted at all (it can be
        # stale across calls, second adversary pass D2)
        if (total is None and entries and live is not None
                and entries[-1]["result"] is None):
            on_disk = entries[-1].get("cli_invocations", 0)
            if live > on_disk:
                invocations += live - on_disk
                accounting = ("session-reported; live count applied to the "
                              "interrupted call")
                reconciliation = {"probe_id": entries[-1].get("probe_id"),
                                  "on_disk_cli_invocations": on_disk,
                                  "live_cli_invocations": live}
                if persisted.get("preflight_result") == "IN-PROGRESS":
                    # the evidence is not yet finalized: correct the entry
                    # before the FAIL sibling is written below
                    entries[-1]["cli_invocations"] = live
        if total is not None and invocations < total:
            # the cumulative total outranks every per-entry figure: the
            # receipt is never lower than the number of invocations the
            # session actually started across all calls (N1)
            missing = total - invocations
            reconciliation = dict(reconciliation or {},
                                  on_disk_total=invocations, live_total=total)
            invocations = total
            accounting = ("session-reported; live total applied "
                          f"({missing} invocation(s) absent from the transcript)")
            if entries and persisted.get("preflight_result") == "IN-PROGRESS":
                entries[-1]["cli_invocations"] = (
                    entries[-1].get("cli_invocations", 0) + missing)
        counts = [t.get("cli_invocations", 0) for t in entries] + [total or 0]
        if any(not isinstance(c, int) or isinstance(c, bool) or c < 0
               for c in counts):
            # a session that reports a negative or non-integer count is
            # publishing garbage; the receipt says so instead of the number
            # (third adversary pass on 18321531, V1: a total that went
            # backwards published "invocations -1" on a PASS)
            invocations = None
            accounting = ("unavailable (session reported an invalid "
                          f"invocation count: {counts})")
            reconciliation = None
    else:
        # the session never reported what it ran; a number here would be
        # the harness's guess published as a receipt (adversary F5)
        invocations = None
        accounting = "unavailable"
    if persisted.get("preflight_result") == "IN-PROGRESS" and result == "FAIL":
        # the harness never finalized (interrupted mid-attempt): ledger the
        # spent attempt as FAIL rather than exit without a line
        persisted["preflight_result"] = "FAIL"
        persisted["failure_reason"] = persisted.get("failure_reason") or error
        canon.write_canonical_atomic(transcript_path, persisted)
        reviewer.persist_failure(transcript_path, persisted)
    if persisted.get("preflight_result") != result:
        raise SystemExit("qualification evidence disagrees with outcome: "
                         f"{persisted.get('preflight_result')!r} vs {result}")
    # the durable evidence is the content-addressed sibling, never the
    # working file (hole 1: the working file is rewritten by the next attempt)
    sibling_manifest = canon.load_json_regular(os.path.join(
        Q_OUT, reviewer.PASSED_PREFLIGHT_MANIFEST if result == "PASS"
        else reviewer.FAILED_PREFLIGHT_MANIFEST))
    evidence_sha = _sha(transcript_path)
    sibling = [m for m in sibling_manifest["members"]
               if m["sha256"] == evidence_sha]
    if len(sibling) != 1 or not canon.is_regular(os.path.join(Q_OUT, sibling[0]["path"])):
        raise SystemExit("qualification evidence has no content-addressed "
                         f"sibling on disk for {evidence_sha}")
    evidence_file = sibling[0]["path"]
    record = {
        "artifact_version": "foundry-pass-2-qualification-attempt/experimental-v0.1",
        "qualification_only": True,
        "eligible_for_binding": False,
        "reviewer_role": "reviewer_a",
        "model_id": MODEL,
        "model_version_or_build": cli_build,
        "head": head,
        "attempt_id": persisted["attempt_id"],
        "started_utc": persisted["started_utc"],
        "result": result,
        "error": error,
        "model_calls": calls,
        "cli_invocations": invocations,
        "invocation_accounting": accounting,
        "invocation_reconciliation": reconciliation,
        "attempts_allowed": QUALIFY_ATTEMPTS,
        "ruled_model_id": ruled_model,
        "stale_transcript_stashed": (os.path.relpath(stale, Q_OUT)
                                     if stale else None),
        "reservation_path": os.path.relpath(reservation, Q_OUT),
        "reservation_sha256": _sha(reservation),
        "failed_probes": persisted.get("failed_probes", []),
        "evidence_path": evidence_file,
        "evidence_sha256": evidence_sha,
        "output_schema_sha256": schema["sha256"],
        "fixture_bindings": digests,
        "harness_sha256": _sha(os.path.join(PASS2, "engine", "reviewer.py")),
        "task_prompt_template_sha256": _sha(os.path.join(
            ARI, "reviewer-task-template-v0.1.md")),
        "system_prompt_sha256": _sha(os.path.join(
            ARI, "reviewer-system-prompt-v0.1.md")),
    }
    rec_sha, _rec_path = write_attempt_record(Q_OUT, record)
    append_ledger(Q_OUT, {
        "attempt_id": record["attempt_id"], "head": head,
        "model": MODEL, "result": result, "model_calls": calls,
        "cli_invocations": invocations,
        "invocation_accounting": accounting,
        "invocation_reconciliation": reconciliation,
        "attempts_allowed": QUALIFY_ATTEMPTS,
        "reservation_path": record["reservation_path"],
        "evidence_path": evidence_file,
        "evidence_sha256": evidence_sha, "record_sha256": rec_sha,
        "started_utc": record["started_utc"]})
    shown = "unverified" if invocations is None else str(invocations)
    print("QUALIFICATION LEDGER LINE:")
    print(f"head {head} | model {MODEL} | attempt {record['attempt_id']} | "
          f"calls {calls} | invocations {shown} (allowed "
          f"{QUALIFY_ATTEMPTS} per call) | result {result} | "
          f"evidence {evidence_sha} ({evidence_file}) | record {rec_sha} | "
          f"reservation {record['reservation_path']}")
    if error:
        print("failure:", error)
    raise SystemExit(0 if result == "PASS" else 1)


def write_run_record_manifest(a_out=None):
    """Content-addressed manifest of every run artifact for Reviewer A:
    probe transcript, identity, each shard run record, each fixed output.
    Rewritten after every run so it always covers the current state."""
    A_OUT = a_out or globals()["A_OUT"]
    members = []
    def add(kind, rel):
        path = os.path.join(A_OUT, rel)
        if os.path.isfile(path):
            members.append({"kind": kind, "path": rel, "sha256": _sha(path),
                            "byte_length": os.path.getsize(path)})
    add("leak-probe-transcript", "leak-probe-transcript.json")
    add("failed-preflight-manifest", reviewer.FAILED_PREFLIGHT_MANIFEST)
    add("passed-preflight-manifest", reviewer.PASSED_PREFLIGHT_MANIFEST)
    for name in sorted(os.listdir(A_OUT)):
        if "-FAILED-" in name and name.endswith(".json"):
            add("failed-preflight-evidence", name)
        elif "-PASSED-" in name and name.endswith(".json"):
            add("passed-preflight-evidence", name)
    add("identity", "reviewer-identity.json")
    for sub, kind in (("run-records", "run-record"), ("outputs", "fixed-output")):
        d = os.path.join(A_OUT, sub)
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                add(kind, os.path.join(sub, name))
    manifest = {"artifact_version": "foundry-pass-2-run-record-manifest/experimental-v0.1",
                "reviewer_role": "reviewer_a", "members": members}
    return canon.write_canonical(os.path.join(A_OUT, "run-record-manifest.json"),
                                 manifest)


def expected_identity_fields():
    """Identity fields the gate checks mechanically for Reviewer A, from
    the bound artifacts themselves."""
    harness = _sha(os.path.join(PASS2, "engine", "reviewer.py"))
    fields = {
        "system_prompt_sha256": _sha(os.path.join(ARI, "reviewer-system-prompt-v0.1.md")),
        "task_prompt_template_sha256": _sha(os.path.join(ARI, "reviewer-task-template-v0.1.md")),
        "output_schema_sha256": _sha(os.path.join(ARI, "reviewer-output-v0.1.schema.json")),
        "harness_sha256": harness,
        "parser_sha256": harness,
        "tool_allowlist_sha256": canon.content_digest([]),
        "settings_sources_sha256": canon.content_digest(""),
    }
    transcript = os.path.join(A_OUT, "leak-probe-transcript.json")
    if os.path.isfile(transcript):
        fields["leak_probe_transcript_sha256"] = _sha(transcript)
    return fields


def status():
    manifest = canon.load_json(os.path.join(OUT, "shard-manifest.json"))
    records_dir = os.path.join(A_OUT, "run-records")
    done = {}
    if os.path.isdir(records_dir):
        for name in os.listdir(records_dir):
            rec = canon.load_json(os.path.join(records_dir, name))
            done[rec["shard_id"]] = rec["verdict"]
    for m in manifest["shards"]:
        print(m["shard_id"], m["record_count"], done.get(m["shard_id"], "pending"))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "identity":
        bind_identity()
    elif mode == "qualify":
        qualify()
    elif mode == "review":
        review(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    else:
        status()
