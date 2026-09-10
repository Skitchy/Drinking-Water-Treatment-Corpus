"""Reviewer A runner. Run from experiments/foundry-pass-2:

    python3 tools/run_reviewer_a.py identity      bind identity record + probes:
                                                  one attempt per exact head
                                                  under a binding ruling
                                                  (FOUNDRY_IDENTITY_RULED_MODEL,
                                                  FOUNDRY_IDENTITY_RULING_ID,
                                                  FOUNDRY_IDENTITY_AUX_MODEL_POLICY
                                                  = reject | accept:<model-id>)
    python3 tools/run_reviewer_a.py review <shard-id> [<shard-id> ...]
                                                  one governed review command
                                                  over exactly the named shards,
                                                  in that order, under a ruling
                                                  (FOUNDRY_REVIEW_RULED_MODEL,
                                                  FOUNDRY_REVIEW_RULING_ID);
                                                  refused unless the tree,
                                                  harness, model, CLI build, and
                                                  configuration match the bound
                                                  identity; one CLI invocation
                                                  per shard, no retry; a claimed
                                                  shard is never re-run
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
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

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
QUALIFY_RECORD_PREFIX = "qualification-attempt-"
QUALIFY_LEDGER = "qualification-ledger.json"
# Identity binding (maintainer authorization discussioncomment-18371886, in
# response to Ari's scope in the project room, 2026-09-09): the binding path
# carries the same at-most-once discipline as the qualify path, keyed by
# exact head under out/reviewer-a/, plus binding-specific requirements: a
# ruling reference, a machine-recorded auxiliary-model policy, an identity
# that is never overwritten, and a same-descriptor read-back before the
# identity is installed.
BINDING_ATTEMPTS = 1
BINDING_RECORD_PREFIX = "binding-attempt-"
BINDING_LEDGER = "binding-ledger.json"
IDENTITY_FILE = "reviewer-identity.json"
IDENTITY_RULED_MODEL_VAR = "FOUNDRY_IDENTITY_RULED_MODEL"
IDENTITY_RULING_VAR = "FOUNDRY_IDENTITY_RULING_ID"
AUX_MODEL_POLICY_VAR = "FOUNDRY_IDENTITY_AUX_MODEL_POLICY"
RULING_ID_RE = re.compile(r"[0-9]{6,12}")
MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")
# Governed review (maintainer authorization discussioncomment-18376129, scope
# from Ari in the project room, 2026-09-09, message 255): the review path
# carries the discipline binding earned. One CLI invocation per shard call;
# selection by explicit ordered shard IDs under a ruling reference; ONE
# immutable command reservation keyed by the ruling ID before any call; an
# immutable per-shard execution claim keyed by shard ID immediately before
# that shard's call (so a crash after the invocation can never re-run the
# shard); the output installed atomically with a same-descriptor read-back
# and THEN an immutable shard record written last, at every exit, attesting
# the output digest or the failure phase; stop on the first failure with a
# terminal command record marking every remaining shard NOT_RUN; the run
# manifest a rebuildable index, never the source of truth.
REVIEW_ATTEMPTS = 1
REVIEW_RULED_MODEL_VAR = "FOUNDRY_REVIEW_RULED_MODEL"
REVIEW_RULING_VAR = "FOUNDRY_REVIEW_RULING_ID"
REVIEW_RESERVATION_PREFIX = "review-ruling-"
REVIEW_LEDGER = "review-ledger.json"
CLAIMS_DIR = "claims"
RUN_RECORDS_DIR = "run-records"
OUTPUTS_DIR = "outputs"
COMMAND_RECORDS_DIR = "command-records"
REVIEW_EVIDENCE_DIRS = (RESERVATIONS_DIR, CLAIMS_DIR, RUN_RECORDS_DIR,
                        OUTPUTS_DIR, COMMAND_RECORDS_DIR)
SHARD_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")


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


def parse_aux_model_policy(value, reviewer_model):
    """The machine-recorded auxiliary-model policy the binding ruling states
    (authorization 18371886; Ari's scope, project room 2026-09-09). The CLI
    is disclosed to make one utility call per session to a title model
    beside the reviewer model (IsolatedSession.environment_boundary,
    honest_limits). The ruling must say what that means for binding, and
    the record must carry the decision rather than leave it implicit:

      reject             no model other than the reviewer model may appear
                         in any invocation's observed model usage; if one
                         does, the attempt is FAIL and no identity is bound
      accept:<model-id>  exactly that auxiliary model may appear, recorded
                         with its disclosed title-only observed role; any
                         other model is still a refusal

    Returns the policy record, or raises SystemExit before anything is
    reserved."""
    if not value:
        raise SystemExit(f"identity binding refused: {AUX_MODEL_POLICY_VAR} is "
                         "not set; the ruling must state 'reject' or "
                         "'accept:<model-id>' for the CLI's auxiliary model call")
    # Honest limit, recorded in the policy itself: no CLI configuration is
    # known that prevents or reroutes the title call, so under either
    # policy the enforcement is by observation of what the CLI reported,
    # and a call that reports no model usage at all is a refusal (the
    # ruling cannot be shown to have been honoured).
    prevention = {"prevention_configuration": None,
                  "enforcement": "by observation of reported modelUsage; an "
                                 "invocation that reports no modelUsage fails "
                                 "the attempt"}
    if value == "reject":
        return dict(prevention, policy="reject", auxiliary_model=None,
                    disclosed_role=None)
    if value.startswith("accept:"):
        model = value[len("accept:"):]
        if MODEL_ID_RE.fullmatch(model) and model not in (reviewer_model, "reject"):
            return dict(prevention, policy="accept", auxiliary_model=model,
                        disclosed_role=("CLI display-title utility call, one "
                                        "per session; observed output is title "
                                        "metadata only (environment_boundary."
                                        "honest_limits); not a reviewer turn"))
    raise SystemExit(f"identity binding refused: {AUX_MODEL_POLICY_VAR}="
                     f"{value[:80]!r} is not 'reject' or 'accept:<model-id>' "
                     "naming a model other than the reviewer model")


def observed_model_usage(persisted):
    """Every model the CLI reported using, per model call, from the raw
    result each transcript entry preserved (`modelUsage`, keyed by model
    id, each carrying a canonicalModel and token counts). An entry without
    a result or without the field reports an empty list and says so
    (`model_usage_reported` false), never a guess: the policy below is a
    check against what the CLI reported, and a CLI that reports nothing
    is recorded as having reported nothing."""
    usage = []
    for entry in persisted.get("transcripts", []):
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        models = []
        if isinstance(result, dict) and isinstance(result.get("modelUsage"), dict):
            for model_id, detail in sorted(result["modelUsage"].items()):
                item = {"model_id": model_id}
                if isinstance(detail, dict):
                    for key in ("canonicalModel", "inputTokens", "outputTokens",
                                "cacheCreationInputTokens",
                                "cacheReadInputTokens"):
                        if key in detail:
                            item[key] = detail[key]
                models.append(item)
        # an empty modelUsage is not a report either: a call that reached a
        # model used at least one (pass two, F1)
        usage.append({"probe_id": entry.get("probe_id"),
                      "model_usage_reported": bool(models),
                      "models": models})
    return usage


def aux_policy_violations(usage, reviewer_model, policy):
    """Model usage the policy does not allow. Every call that reports usage
    must report the ruled reviewer model by its exact id (Ari, exact-diff
    review of 42bf839, blocking finding 1: an accepted auxiliary model is
    additional, never a substitute); under accept, the auxiliary model the
    ruling names is allowed by its exact id (the id the CLI reports, not a
    canonical alias, which is the entry's own claim); anything else is a
    violation."""
    aux = ({policy.get("auxiliary_model")} if policy.get("policy") == "accept"
           else set())
    violations = []
    for call in usage:
        ids = [item["model_id"] for item in call["models"]]
        if ids and reviewer_model not in ids:
            violations.append(f"{call['probe_id']}: reviewer model "
                              f"{reviewer_model} not reported")
        for item in call["models"]:
            if item["model_id"] == reviewer_model:
                tokens = [item.get(k) for k in ("inputTokens", "outputTokens",
                                                "cacheReadInputTokens",
                                                "cacheCreationInputTokens")]
                if not any(isinstance(t, int) and not isinstance(t, bool) and t > 0
                           for t in tokens):
                    # the ruled model is named but credited with no work:
                    # not a credible report of a call (pass three, finding 4)
                    violations.append(f"{call['probe_id']}: reviewer model "
                                      f"{reviewer_model} reported with no tokens")
        for model_id in ids:
            if model_id == reviewer_model or model_id in aux:
                continue
            violations.append(f"{call['probe_id']}: {model_id}")
    return violations

os_link = os.link  # single seam so tests can plant a file between check and install


def install_identity_readback(path, obj):
    """Install the identity record exactly once, verified from the same
    descriptor that wrote it (authorization 18371886: same-fd readback
    before atomic identity install; no identity overwrite).

    Sequence: refuse if anything exists at `path` (lstat, never followed);
    canonical bytes to a same-directory temporary file through write_all;
    fsync; the fstat size must equal the payload; every byte is then read
    back from the SAME open descriptor with pread and must equal the
    payload (a size check proves length, not content, and this digest
    becomes the trust root of every review prompt); the digest is computed
    from the bytes read back, not from the buffer; the file is installed
    with link(), which never replaces an existing name, so a file that
    appears between the check and the install is a refusal rather than an
    overwrite; the directory is fsynced; the installed path is read once
    more without following links and must hold the same bytes.

    Identity-specific by design: the shared atomic writer keeps its size
    check, and this primitive is not used for mutable manifests."""
    if os.path.lexists(path):
        raise SystemExit(f"identity binding refused: {os.path.basename(path)} "
                         "already exists; an identity is never overwritten "
                         "(bind into a fresh evidence root)")
    data = canon.canonical_bytes(obj)
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".tmp-identity-", suffix=".json",
                               dir=directory)
    try:
        canon.write_all(fd, data, "identity temporary file")
        os.fsync(fd)
        on_disk = os.fstat(fd).st_size
        if on_disk != len(data):
            raise canon.ShortWriteError(
                f"identity temporary file: {on_disk} byte(s) on disk for a "
                f"{len(data)} byte payload after fsync; refusing to install")
        back = bytearray()
        while len(back) < len(data):
            chunk = os.pread(fd, min(65536, len(data) - len(back)), len(back))
            if not chunk:
                raise canon.ShortWriteError(
                    f"identity temporary file: read back ended after "
                    f"{len(back)} of {len(data)} byte(s); refusing to install")
            back += chunk
        if os.pread(fd, 1, len(data)) != b"":
            raise canon.ShortWriteError(
                "identity temporary file: more bytes on disk than the "
                "payload; refusing to install")
        if bytes(back) != data:
            raise canon.ShortWriteError(
                "identity temporary file: bytes read back from the same "
                "descriptor differ from the payload; refusing to install")
        digest = canon.bytes_digest(bytes(back))
        os.fchmod(fd, 0o644)
        os.close(fd)
        fd = None
        try:
            os_link(tmp, path)
        except FileExistsError:
            raise SystemExit(f"identity binding refused: {os.path.basename(path)} "
                             "appeared during install and was not overwritten")
        except OSError as err:
            raise SystemExit(f"identity binding refused: {os.path.basename(path)} "
                             f"could not be installed by link ({err}); nothing "
                             "was installed")
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    dfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    try:
        installed = canon.read_regular_bytes(path)
    except (OSError, canon.PathBoundaryError) as err:
        installed = None
        detail = f"{type(err).__name__}: {err}"
    else:
        detail = "bytes differ"
    if installed != data:
        # refused and installed must not both be true: the bytes at the
        # identity name are moved aside under a name that says so, best
        # effort, before the refusal (isolated adversary, finding 8)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        n = 0
        while True:
            quarantine = os.path.join(
                directory, f"reviewer-identity-REFUSED-{stamp}-{n}.json")
            if not os.path.lexists(quarantine):
                break
            n += 1
        moved = None
        if os.path.lexists(path):
            try:
                os.rename(path, quarantine)
                moved = os.path.basename(quarantine)
            except OSError:
                moved = None
        raise SystemExit(f"identity binding refused: {os.path.basename(path)} "
                         f"on disk does not hold the verified bytes after "
                         f"install ({detail}); "
                         + (f"moved to {moved}" if moved else
                            "nothing was moved (the path was absent or the "
                            "move failed)"))
    return digest


def bind_identity(out_root=None, a_out=None, session_factory=None):
    """Bind the Reviewer A identity: the five leak probes against the real
    bundle, then the identity record every review prompt carries. One
    attempt per exact head, under the discipline of qualify() (authorized
    by 18371886): every deterministic check runs BEFORE a binding-specific
    reservation spends the head; the session allows exactly one CLI
    invocation per probe call and must say so; every outcome, interrupt
    included, leaves an immutable attempt record with the head, the ruling
    reference, the reservation and evidence digests, the invocation
    accounting, and the observed model usage; a stale working transcript
    is stashed, never attributed; the auxiliary-model policy the ruling
    states is checked against what the CLI reported; the identity is
    written once through a same-descriptor read-back and never
    overwritten. Reads the bundle under out_root; writes ONLY under a_out."""
    out_root = out_root or OUT
    a_out = a_out or A_OUT
    session_factory = session_factory or make_session
    what = "identity binding"
    if not os.path.isfile(os.path.join(out_root, "review-input-bundle.json")):
        raise SystemExit(f"{what} refused: review-input bundle missing under "
                         f"{os.path.relpath(out_root, PASS2)}")
    head, clean = git_head(what)
    if not valid_head(head):
        raise SystemExit(f"{what} refused: {str(head)[:60]!r} is not a 40-hex "
                         "commit sha")
    if not clean:
        raise SystemExit(f"{what} refused: working tree is not clean at {head}")
    ruled_model = os.environ.get(IDENTITY_RULED_MODEL_VAR, "")
    if not ruled_model:
        raise SystemExit(f"{what} refused: {IDENTITY_RULED_MODEL_VAR} is not "
                         "set; state the model ID the binding ruling names")
    if ruled_model != MODEL:
        raise SystemExit(f"{what} refused: the ruling names model "
                         f"{ruled_model!r} but the harness would run {MODEL!r}")
    ruling_id = os.environ.get(IDENTITY_RULING_VAR, "")
    if not RULING_ID_RE.fullmatch(ruling_id):
        raise SystemExit(f"{what} refused: {IDENTITY_RULING_VAR}="
                         f"{ruling_id[:40]!r} is not a discussion comment ID "
                         "(6 to 12 digits); name the maintainer ruling")
    policy = parse_aux_model_policy(os.environ.get(AUX_MODEL_POLICY_VAR, ""),
                                    MODEL)
    # path-boundary gate BEFORE anything under the evidence root is read or
    # created: the root, its ancestors below the pass root, the
    # reservations directory, and every pre-existing entry are inspected
    # with lstat; a run-records or outputs directory is a refusal too,
    # because review artifacts cannot predate the identity they bind to
    problems = check_evidence_paths(a_out)
    if problems:
        raise SystemExit(f"{what} refused: evidence path boundary: "
                         + "; ".join(problems))
    os.makedirs(a_out, exist_ok=True)
    identity_path = os.path.join(a_out, IDENTITY_FILE)
    if os.path.lexists(identity_path):
        raise SystemExit(f"{what} refused: {IDENTITY_FILE} already exists in "
                         f"{os.path.relpath(a_out, PASS2)}; an identity is "
                         "never overwritten (bind into a fresh evidence root)")
    refuse_if_spent(a_out, head, BINDING_RECORD_PREFIX, BINDING_LEDGER, what)
    # input identities are read BEFORE the attempt, so anything that can
    # fail here fails with nothing spent
    cli_build = cli_version()
    system_prompt_path = os.path.join(ARI, "reviewer-system-prompt-v0.1.md")
    system_prompt = _read(system_prompt_path)
    template = load_template(out_root)
    digests = bundle_digests(out_root)
    schema = load_schema(out_root)
    harness_sha = _sha(os.path.join(PASS2, "engine", "reviewer.py"))
    # every deterministic check has passed; from here the head is spent
    # whatever happens next, and every exit writes ONE immutable binding
    # attempt record that says what actually happened, including whether
    # the identity was installed and with which digest (Ari, exact-diff
    # review of 42bf839, blocking finding 3: a record written before the
    # install said PASS for an install that failed, and refusals after the
    # reservation left no record at all)
    reserved_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    reservation = reserve_head(a_out, head, {
        "reserved_utc": reserved_utc,
        "purpose": "identity-binding",
        "model_id": MODEL, "ruled_model_id": ruled_model,
        "ruling_id": ruling_id,
        "model_version_or_build": cli_build,
        "bindings": digests, "attempts_allowed": BINDING_ATTEMPTS,
        "auxiliary_model_policy": policy,
        "harness_sha256": harness_sha},
        artifact_version="foundry-pass-2-binding-reservation/experimental-v0.1",
        what=what)
    outcome = {
        "artifact_version": "foundry-pass-2-binding-attempt/experimental-v0.2",
        "purpose": "identity-binding",
        "reviewer_role": "reviewer_a",
        "model_id": MODEL,
        "model_version_or_build": cli_build,
        "head": head,
        "ruling_id": ruling_id,
        "ruled_model_id": ruled_model,
        "attempt_id": None,
        "started_utc": reserved_utc,
        "result": None,
        "phase": "reserved",
        "error": None,
        "model_calls": 0,
        "cli_invocations": None,
        "invocation_accounting": "unavailable",
        "invocation_reconciliation": None,
        "live_invocations_started": None,
        "attempts_allowed": BINDING_ATTEMPTS,
        "auxiliary_model_policy": policy,
        "auxiliary_model_violations": [],
        "observed_model_usage": [],
        "stale_transcript_stashed": None,
        "reservation_path": os.path.relpath(reservation, a_out),
        "reservation_sha256": _sha(reservation),
        "failed_probes": [],
        "evidence_path": None,
        "evidence_sha256": None,
        "output_schema_sha256": schema["sha256"],
        "bindings": digests,
        "harness_sha256": harness_sha,
        "task_prompt_template_sha256": _sha(os.path.join(
            ARI, "reviewer-task-template-v0.1.md")),
        "system_prompt_sha256": _sha(system_prompt_path),
        "leak_probes_sha256": None,
        "session_ids_sha256": None,
        "identity_path": IDENTITY_FILE,
        "identity_sha256": None,
    }

    def refuse(message):
        outcome["result"] = "REFUSED"
        outcome["error"] = message
        raise SystemExit(message)

    try:
        outcome["phase"] = "stash"
        stale = stash_stale_transcript(a_out, head)
        outcome["stale_transcript_stashed"] = (os.path.relpath(stale, a_out)
                                              if stale else None)
        prior_ids = known_attempt_ids(a_out, BINDING_RECORD_PREFIX, BINDING_LEDGER)
        cwd = tempfile.mkdtemp(prefix="foundry-reviewer-a-bind-")
        outcome["phase"] = "session-construction"
        try:
            session = session_factory(system_prompt, cwd, BINDING_ATTEMPTS)
        except BaseException as err:  # noqa: B036 - zero-call, reported as such
            refuse(f"{what} did not start an attempt: session construction "
                   f"failed: {type(err).__name__}: {str(err)[:300]} (head "
                   "stays reserved)")
        # the session must SAY what it allows and what it runs; one that does
        # not expose its retry policy or its command line cannot be bound
        if getattr(session, "attempts", None) != BINDING_ATTEMPTS:
            refuse(f"{what} refused before any call: session reports "
                   f"attempts={getattr(session, 'attempts', None)!r}; the "
                   f"ruling allows exactly {BINDING_ATTEMPTS} (head stays "
                   "reserved)")
        if not (callable(getattr(session, "command", None))
                and callable(getattr(session, "environment_boundary", None))
                and isinstance(getattr(session, "timeout", None), int)
                and not isinstance(getattr(session, "timeout", None), bool)
                and getattr(session, "timeout", 0) > 0):
            refuse(f"{what} refused before any call: session does not expose "
                   "its command, environment boundary, and a positive timeout; "
                   "the identity cannot bind a configuration it cannot see "
                   "(head stays reserved)")
        # Probes run with a provisional identity digest (all zeros): the
        # probe prompts are not reviews, and the bound identity includes
        # the probe transcript digest, so it cannot exist before the probes.
        probe_digests = dict(digests, REVIEWER_IDENTITY_SHA256="0" * 64)
        transcript_path = os.path.join(a_out, "leak-probe-transcript.json")
        outcome["phase"] = "probes"
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
        except BaseException as err:  # noqa: B036 - a spent attempt is recorded
            result = "FAIL"
            error = f"harness aborted: {type(err).__name__}: {str(err)[:400]}"
        outcome["result"] = result
        outcome["error"] = error
        # the live count the session holds, kept on the record even when the
        # evidence on disk is lost and reconcile_attempt refuses below
        live_total = getattr(session, "total_invocations", None)
        live_last = getattr(session, "last_invocations", None)
        started = live_total if isinstance(live_total, int) else live_last
        outcome["live_invocations_started"] = (
            started if isinstance(started, int) and not isinstance(started, bool)
            else None)
        outcome["phase"] = "reconcile"
        receipt = reconcile_attempt(session, transcript_path, result, error,
                                    prior_ids, what)
        persisted = receipt["persisted"]
        usage = observed_model_usage(persisted)
        violations = aux_policy_violations(usage, MODEL, policy)
        unreported = [u["probe_id"] for u in usage if not u["model_usage_reported"]]
        invocations = receipt["invocations"]
        per_call = [t.get("cli_invocations") for t in persisted["transcripts"]
                    if t.get("result") is not None]
        if violations and result == "PASS":
            # the probes passed but the CLI reported usage the ruling does
            # not allow, or did not report the ruled reviewer model: the
            # attempt is spent and recorded, and no identity is bound
            result = "FAIL"
            error = ("auxiliary model policy violated: observed "
                     + "; ".join(violations))[:500]
        elif unreported and result == "PASS":
            # a call that reports no model usage cannot show the policy was
            # honoured (isolated adversary on this head, finding 3)
            result = "FAIL"
            error = ("auxiliary model policy could not be checked: no "
                     f"modelUsage reported for {unreported}")[:500]
        if result == "PASS" and not isinstance(invocations, int):
            # a bound identity may not rest on a count the session could
            # not or would not report (pass two, F5)
            result = "FAIL"
            error = ("invocation count unavailable: the session did not "
                     "report a valid CLI invocation count; the ruling's "
                     f"budget cannot be shown to have held "
                     f"({receipt['accounting']})")[:500]
        if result == "PASS" and (
                invocations != receipt["calls"] * BINDING_ATTEMPTS
                or any(c != BINDING_ATTEMPTS for c in per_call)):
            # counting is not enforcement (Ari 18321030): every successful
            # probe call must have made exactly one CLI invocation and the
            # total must reconcile; zero, more, or a mismatch has broken the
            # ruling's sentence (Ari, review of 42bf839, blocking finding 2)
            result = "FAIL"
            error = (f"invocation accounting does not match the ruling: "
                     f"{invocations} CLI invocation(s) for {receipt['calls']} "
                     f"probe call(s), per call {per_call}; the ruling allows "
                     f"exactly {BINDING_ATTEMPTS} per call")
        outcome.update({
            "attempt_id": persisted["attempt_id"],
            "started_utc": persisted["started_utc"],
            "result": result,
            "error": error,
            "model_calls": receipt["calls"],
            "cli_invocations": invocations,
            "invocation_accounting": receipt["accounting"],
            "invocation_reconciliation": receipt["reconciliation"],
            "auxiliary_model_violations": violations,
            "observed_model_usage": usage,
            "failed_probes": persisted.get("failed_probes", []),
            "evidence_path": receipt["evidence_file"],
            "evidence_sha256": receipt["evidence_sha"],
            "leak_probes_sha256": canon.content_digest(persisted.get("records", [])),
            "session_ids_sha256": canon.content_digest(
                [(t.get("result") or {}).get("session_id")
                 for t in persisted.get("transcripts", [])]),
        })
        if result == "PASS":
            outcome["phase"] = "install"
            boundary = session.environment_boundary()
            configuration = {"command": session.command()[:-1] + ["<system prompt>"],
                             "timeout_s": session.timeout}
            identity = {
                "artifact_version": "foundry-pass-2-reviewer-identity/experimental-v0.2",
                "reviewer_role": "reviewer_a",
                "operator_lineage": "CC (Claude Code harness); fresh headless role "
                                    "sessions, not the interactive or builder session",
                "model_provider": "Anthropic",
                "model_id": MODEL,
                "ruled_model_id": ruled_model,
                "ruling_id": ruling_id,
                "model_version_or_build": cli_build,
                "head": head,
                "system_prompt_sha256": outcome["system_prompt_sha256"],
                "task_prompt_template_sha256": outcome["task_prompt_template_sha256"],
                "output_schema_sha256": schema["sha256"],
                "output_schema_model_visible": True,
                "harness_sha256": harness_sha,
                "parser_sha256": harness_sha,
                "tool_allowlist_sha256": canon.content_digest([]),
                "settings_sources_sha256": canon.content_digest(""),
                "configuration_sha256": canon.content_digest(configuration),
                "environment_boundary_sha256": canon.content_digest(boundary),
                "leak_probe_transcript_sha256": receipt["evidence_sha"],
                "leak_probe_evidence_path": receipt["evidence_file"],
                "leak_probes_sha256": outcome["leak_probes_sha256"],
                "session_ids_sha256": outcome["session_ids_sha256"],
                "bound_before_first_real_review": True,
                "eligible_for_binding": True,
                "qualification_only": False,
                "binding_attempts_allowed": BINDING_ATTEMPTS,
                # the identity names its attempt; the record, written after
                # the install, names the identity's digest; no cycle
                "binding_attempt_id": persisted["attempt_id"],
                "reservation_path": outcome["reservation_path"],
                "reservation_sha256": outcome["reservation_sha256"],
                "auxiliary_model_policy": policy,
                "observed_model_usage": usage,
                "bindings": digests,
                "configuration": configuration,
                "environment_boundary": boundary,
                "leak_probes": persisted["records"],
            }
            outcome["identity_sha256"] = install_identity_readback(identity_path, identity)
            write_run_record_manifest(a_out)
        outcome["phase"] = "finalized"
    except SystemExit as err:
        if outcome["identity_sha256"] is None and outcome["result"] != "REFUSED":
            outcome["result"] = "FAIL"
            message = f"{err.code}"[:500]
            if outcome["phase"] == "install":
                message = f"identity not installed: {err.code}"[:500]
            outcome["error"] = (f"{outcome['error']}; {message}"[:800]
                                if outcome["error"] and message not in outcome["error"]
                                else message)
        raise
    except BaseException as err:  # noqa: B036 - recorded, then propagated
        if outcome["identity_sha256"] is None:
            outcome["result"] = "FAIL"
            outcome["error"] = (f"harness aborted during {outcome['phase']}: "
                                f"{type(err).__name__}: {str(err)[:400]}")
            if outcome["phase"] == "install" and isinstance(err, OSError):
                # a write, fsync, size, read-back, or link failure while
                # installing is a refusal in the harness's words, recorded
                # as such, not a traceback; the attempt is spent
                outcome["error"] = (f"identity not installed: "
                                    f"{type(err).__name__}: {str(err)[:400]}")
                raise SystemExit(f"{what} refused: {outcome['error']}") from None
        else:
            outcome["error"] = (outcome["error"] or
                                f"after install: {type(err).__name__}: "
                                f"{str(err)[:300]}")
        raise
    finally:
        finalize_binding_attempt(a_out, outcome)
    raise SystemExit(0 if outcome["result"] == "PASS" else 1)


def finalize_binding_attempt(a_out, outcome):
    """Write the one immutable binding attempt record for this attempt,
    append the ledger projection, and print the ledger line. Runs on every
    post-reservation exit. A record for this attempt (by attempt id, or by
    reservation digest when no attempt started) is never written twice; an
    interrupt inside the record write is retried once with the interruption
    named, then propagated unchanged."""
    live = outcome["live_invocations_started"]
    if (outcome["cli_invocations"] is None and outcome["evidence_sha256"] is None
            and isinstance(live, int) and live > 0):
        # the evidence on disk was lost after a call started: the record
        # keeps the session's live count rather than nothing
        outcome["cli_invocations"] = live
        outcome["invocation_accounting"] = ("live count applied; evidence "
                                            "on disk was not available")
    key_field, key = (("attempt_id", outcome["attempt_id"])
                      if outcome["attempt_id"] else
                      ("reservation_sha256", outcome["reservation_sha256"]))

    def existing():
        for name in os.listdir(a_out):
            if name.startswith(BINDING_RECORD_PREFIX) and name.endswith(".json"):
                try:
                    rec = canon.load_json_regular(os.path.join(a_out, name))
                except Exception:  # noqa: BLE001
                    continue
                if rec.get(key_field) == key and (
                        key_field == "attempt_id" or not rec.get("attempt_id")):
                    return name[len(BINDING_RECORD_PREFIX):-5]
        return None

    rec_sha = existing()
    if rec_sha is None:
        try:
            rec_sha, _rec_path = write_binding_record(a_out, outcome)
        except BaseException as err:  # noqa: B036 - the record is the evidence
            try:
                if existing() is None:
                    write_binding_record(a_out, dict(
                        outcome, record_write_interrupted=f"{type(err).__name__}: "
                                                          f"{str(err)[:200]}"))
            except BaseException:  # noqa: B036, BLE001 - best effort only
                pass
            raise
    append_binding_ledger(a_out, {
        "attempt_id": outcome["attempt_id"], "head": outcome["head"],
        "ruling_id": outcome["ruling_id"], "model": outcome["model_id"],
        "result": outcome["result"], "phase": outcome["phase"],
        "model_calls": outcome["model_calls"],
        "cli_invocations": outcome["cli_invocations"],
        "invocation_accounting": outcome["invocation_accounting"],
        "invocation_reconciliation": outcome["invocation_reconciliation"],
        "attempts_allowed": outcome["attempts_allowed"],
        "auxiliary_model_policy": outcome["auxiliary_model_policy"]["policy"],
        "auxiliary_model_violations": outcome["auxiliary_model_violations"],
        "reservation_path": outcome["reservation_path"],
        "evidence_path": outcome["evidence_path"],
        "evidence_sha256": outcome["evidence_sha256"],
        "record_sha256": rec_sha,
        "identity_sha256": outcome["identity_sha256"],
        "started_utc": outcome["started_utc"]})
    shown = ("unverified" if outcome["cli_invocations"] is None
             else str(outcome["cli_invocations"]))
    print("IDENTITY BINDING LEDGER LINE:")
    print(f"head {outcome['head']} | ruling {outcome['ruling_id']} | model "
          f"{outcome['model_id']} | attempt {outcome['attempt_id'] or 'none'} | "
          f"calls {outcome['model_calls']} | invocations {shown} (allowed "
          f"{outcome['attempts_allowed']} per call) | aux-policy "
          f"{outcome['auxiliary_model_policy']['policy']} | result "
          f"{outcome['result']} | evidence {outcome['evidence_sha256'] or 'none'}"
          f" ({outcome['evidence_path'] or 'none'}) | record {rec_sha} | identity "
          f"{outcome['identity_sha256'] or 'none'} | reservation "
          f"{outcome['reservation_path']}")
    if outcome["error"]:
        print("failure:", outcome["error"])
    if outcome["identity_sha256"]:
        print("REVIEWER_IDENTITY_SHA256:", outcome["identity_sha256"])

def select_by_id(manifest, shard_ids, what="review"):
    """The ordered members the ruling names, or a refusal. Selection by
    count is gone (authorization 18376129): a ruling names exact shard IDs,
    and the command honours exactly that list in that order. Duplicate and
    unknown IDs are refused here, before anything is reserved."""
    if isinstance(shard_ids, (int, str)) or not isinstance(shard_ids, (list, tuple)) \
            or not shard_ids:
        raise SystemExit(f"{what} refused: selection must be a non-empty list "
                         "of explicit shard IDs named by the ruling; selection "
                         "by count is not authorized")
    seen = set()
    for sid in shard_ids:
        if not isinstance(sid, str) or not SHARD_ID_RE.fullmatch(sid):
            raise SystemExit(f"{what} refused: {str(sid)[:60]!r} is not a shard "
                             "ID")
        if sid in seen:
            raise SystemExit(f"{what} refused: shard ID {sid} is named more "
                             "than once")
        seen.add(sid)
    by_id = {m["shard_id"]: m for m in manifest["shards"]}
    unknown = [sid for sid in shard_ids if sid not in by_id]
    if unknown:
        raise SystemExit(f"{what} refused: shard ID(s) not in the bound "
                         f"manifest: {unknown}")
    return [by_id[sid] for sid in shard_ids]


def claimed_shard_ids(a_out):
    """Every shard ID that any durable trace under a_out already spends:
    a claim (any object at claims/<id>.json, by existence, never parsed to
    decide), a shard record (by its CONTENT's shard_id, and by the name
    part before the digest; a record whose name and content disagree
    spends both), or an installed output (outputs/<id>.json). Any one is
    sufficient to refuse. Temporary files (a leading dot) are not traces
    (isolated adversary on this head, findings 7 and 12)."""
    spent = set()
    claims = os.path.join(a_out, CLAIMS_DIR)
    if canon.is_real_dir(claims):
        for name in os.listdir(claims):
            if name.endswith(".json") and not name.startswith("."):
                spent.add(name[:-5])
    records = os.path.join(a_out, RUN_RECORDS_DIR)
    if canon.is_real_dir(records):
        for name in os.listdir(records):
            if not name.endswith(".json") or name.startswith("."):
                continue
            if "." in name[:-5]:
                spent.add(name[:-5].rsplit(".", 1)[0])
            try:
                rec = canon.load_json_regular(os.path.join(records, name))
            except Exception:  # noqa: BLE001 - reported by store_problems
                continue
            if isinstance(rec, dict) and isinstance(rec.get("shard_id"), str):
                spent.add(rec["shard_id"])
    outputs = os.path.join(a_out, OUTPUTS_DIR)
    if canon.is_real_dir(outputs):
        for name in os.listdir(outputs):
            if name.endswith(".json") and not name.startswith("."):
                spent.add(name[:-5])
    return spent


RECORD_NAME_RE = re.compile(r"(.+)\.([0-9a-f]{64})\.json")


def review_store_problems(a_out):
    """Anything under the review directories that the harness did not
    write in the shape it writes: a shard record whose name is not
    <shard_id>.<sha256>.json, whose content is unreadable, or whose
    content names another shard; a command record likewise; a leftover
    temporary file. Every one is reported, and a command refuses on any
    (isolated adversary on this head, finding 7: a record named
    <shard_id>.json spent a different ID than the one it named)."""
    problems = []
    if canon.is_real_dir(a_out):
        # the evidence root itself: the temporaries land here, and so do
        # quarantined outputs; either one refuses the next command until a
        # maintainer has looked (second isolated pass, findings 1 and 7)
        for name in sorted(os.listdir(a_out)):
            if name.startswith("."):
                problems.append(f"{name}: leftover temporary file")
            elif name.startswith("REFUSED-"):
                problems.append(f"{name}: quarantined bytes from a refused install")
    for sub in REVIEW_EVIDENCE_DIRS:
        d = os.path.join(a_out, sub)
        if not canon.is_real_dir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith("."):
                problems.append(f"{sub}/{name}: leftover temporary file")
                continue
            if sub == OUTPUTS_DIR and not (name.endswith(".json")
                                           and SHARD_ID_RE.fullmatch(name[:-5])
                                           and "-REFUSED-" not in name):
                # the gate reads every file here: only <shard_id>.json is
                # ever written here (second pass, finding 1)
                problems.append(f"{sub}/{name}: not a shard output the harness wrote")
                continue
            if sub not in (RUN_RECORDS_DIR, COMMAND_RECORDS_DIR):
                continue
            m = RECORD_NAME_RE.fullmatch(name)
            if m is None:
                problems.append(f"{sub}/{name}: not a content-addressed record name")
                continue
            try:
                data = canon.read_regular_bytes(os.path.join(d, name))
                rec = json.loads(data.decode("utf-8"))
            except Exception as err:  # noqa: BLE001
                problems.append(f"{sub}/{name}: unreadable ({type(err).__name__})")
                continue
            if canon.bytes_digest(data) != m.group(2):
                # the name's digest part is the bytes' digest, exactly the
                # shape the harness writes (second pass, note 8: a greedy
                # match let <id>.<hex>.<hex>.json through)
                problems.append(f"{sub}/{name}: does not hash to its name")
                continue
            key = "shard_id" if sub == RUN_RECORDS_DIR else "command_attempt_id"
            if not isinstance(rec, dict) or rec.get(key) != m.group(1):
                problems.append(f"{sub}/{name}: content names "
                                f"{(rec or {}).get(key)!r}, not {m.group(1)!r}")
    return problems


def preverify_selection(selected, out_root):
    """Ari exact-diff review of 7b6d454 (discussioncomment-18206472): every
    selected shard is digest-checked against the manifest AND has every
    record's identity recomputed (reviewer.verify_shard_records) BEFORE any
    reviewer session is constructed or any model call is made. A failure on
    any shard aborts the whole review command; it is never swallowed into
    the per-shard continuation path. Returns {shard_id: verification list}."""
    verified = {}
    for member in selected:
        shard_path = bound_shard_path(out_root, member)
        if not canon.is_regular(shard_path):
            raise SystemExit(f"review aborted before any session: shard "
                             f"{member['shard_id']} input is absent or not a "
                             f"regular file ({member['path']})")
        if canon.bytes_digest(canon.read_regular_bytes(shard_path)) != member["sha256"]:
            raise SystemExit(f"review aborted before any session: shard "
                             f"digest drift: {member['shard_id']}")
        shard = canon.load_json_regular(shard_path)
        try:
            verified[member["shard_id"]] = reviewer.verify_shard_records(shard)
        except reviewer.ReviewerError as err:
            raise SystemExit(f"review aborted before any session: "
                             f"{str(err)[:600]}")
    return verified


def bound_shard_path(out_root, member):
    """The on-disk path of a manifest member, refused unless it is a
    relative, normalized path that stays under out_root (isolated
    adversary on this head, finding 1: a manifest row with '../' named a
    file outside the bundle root and it was read)."""
    rel = member.get("path")
    if (not isinstance(rel, str) or not rel or os.path.isabs(rel)
            or os.path.normpath(rel) != rel or rel.startswith("..")
            or ".." in rel.split("/") or "\\" in rel):
        raise SystemExit(f"review refused: shard {member.get('shard_id')!r} "
                         f"names a path outside the bundle root: {rel!r}")
    root = os.path.realpath(out_root)
    full = os.path.join(root, rel)
    # every directory component under the root is inspected with lstat: a
    # symlinked directory would carry the read outside the root while the
    # leaf's own no-follow guard held (second isolated pass, finding 6)
    cur = root
    for part in rel.split("/")[:-1]:
        cur = os.path.join(cur, part)
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            raise SystemExit(f"review refused: shard {member.get('shard_id')!r} "
                             f"names a path whose directory is absent: {rel!r}")
        if not stat.S_ISDIR(st.st_mode):
            raise SystemExit(f"review refused: shard {member.get('shard_id')!r} "
                             f"names a path through a non-directory or a link: "
                             f"{rel!r}")
    if os.path.commonpath([root, os.path.realpath(full)]) != root:
        raise SystemExit(f"review refused: shard {member.get('shard_id')!r} "
                         f"names a path outside the bundle root: {rel!r}")
    return full


def load_bound_shard_manifest(out_root, digests, what="review"):
    """shard-manifest.json read without following links and REQUIRED to
    hash to the digest the bundle (and so the identity) binds. Before
    this, the bundle's self-declared digest was trusted and the file on
    disk never hashed, so an edited manifest could name a shard the
    ruling never named and send the same bytes to the model twice
    (isolated adversary on this head, finding 1)."""
    path = os.path.join(out_root, "shard-manifest.json")
    if not canon.is_regular(path):
        raise SystemExit(f"{what} refused: shard-manifest.json is absent or "
                         "not a regular file")
    data = canon.read_regular_bytes(path)
    digest = canon.bytes_digest(data)
    if digest != digests["SHARD_MANIFEST_SHA256"]:
        raise SystemExit(f"{what} refused: shard-manifest.json hashes to "
                         f"{digest}; the bundle binds "
                         f"{digests['SHARD_MANIFEST_SHA256']}; the manifest "
                         "on disk is not the bound manifest")
    manifest = json.loads(data.decode("utf-8"))
    ids = [m.get("shard_id") for m in manifest.get("shards", [])]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{what} refused: the bound manifest names a shard "
                         "ID more than once")
    return manifest


def review(shard_ids, session_factory=None, out_root=None, a_out=None):
    """One governed review command over the exact ordered shard IDs a
    maintainer ruling names (authorization 18376129). Every deterministic
    check below runs before anything is reserved; the command reservation
    keyed by the ruling ID spends the ruling; each shard is claimed
    immediately before its one CLI invocation; every post-reservation exit
    leaves a terminal command record, and every claimed shard leaves an
    immutable shard record written after its output. Reads the bundle under
    out_root; writes ONLY under a_out."""
    out_root = out_root or OUT
    a_out = a_out or A_OUT
    session_factory = session_factory or make_session
    identity_path = os.path.join(a_out, "reviewer-identity.json")
    if os.path.lexists(identity_path) and not canon.is_regular(identity_path):
        raise SystemExit("review refused: reviewer-identity.json is not a "
                         "regular file; the identity is never read through a "
                         "link")
    if not canon.is_regular(identity_path):
        raise SystemExit("identity not bound; run `identity` first")
    identity_bytes = canon.read_regular_bytes(identity_path)
    digests = dict(bundle_digests(out_root),
                   REVIEWER_IDENTITY_SHA256=canon.bytes_digest(identity_bytes))
    identity = json.loads(identity_bytes.decode("utf-8"))
    if identity.get("eligible_for_binding") is not True or identity.get(
            "qualification_only") is not False:
        raise SystemExit("identity is a qualification identity, ineligible "
                         "for review")
    bindings = identity.get("bindings")
    expected = {k: v for k, v in digests.items() if k != "REVIEWER_IDENTITY_SHA256"}
    if not isinstance(bindings, dict) or bindings != expected:
        raise SystemExit("bundle changed since identity was bound; rebind")
    schema = load_schema(out_root)
    if schema["sha256"] != identity.get("output_schema_sha256"):
        raise SystemExit("output schema changed since identity was bound")
    system_prompt = _read(os.path.join(ARI, "reviewer-system-prompt-v0.1.md"))
    # review-time enforcement of the bound head and configuration
    # (18371886): a review never runs against an identity whose head,
    # harness, model, CLI build, configuration, or evidence has drifted
    enforce_bound_identity(identity, a_out, system_prompt,
                           digests["REVIEWER_IDENTITY_SHA256"])
    what = "review"
    identity_sha = digests["REVIEWER_IDENTITY_SHA256"]
    # the ruling reference and the ruled model, after the identity checks
    # (nothing is spent either way, and the identity is the trust root)
    ruled_model = os.environ.get(REVIEW_RULED_MODEL_VAR, "")
    if not ruled_model:
        raise SystemExit(f"{what} refused: {REVIEW_RULED_MODEL_VAR} is not "
                         "set; state the model ID the review ruling names")
    if ruled_model != MODEL or ruled_model != identity["model_id"]:
        raise SystemExit(f"{what} refused: the ruling names model "
                         f"{ruled_model!r}; the harness would run {MODEL!r} "
                         f"and the identity binds {identity['model_id']!r}")
    ruling_id = os.environ.get(REVIEW_RULING_VAR, "")
    if not RULING_ID_RE.fullmatch(ruling_id):
        raise SystemExit(f"{what} refused: {REVIEW_RULING_VAR}="
                         f"{ruling_id[:40]!r} is not a discussion comment ID "
                         "(6 to 12 digits); name the maintainer ruling")
    template = load_template(out_root)
    manifest = load_bound_shard_manifest(out_root, digests, what)
    selected = select_by_id(manifest, shard_ids, what)
    for member in selected:
        bound_shard_path(out_root, member)
    # path-boundary gate over the whole evidence root, every directory the
    # review path writes included, BEFORE anything under it is read to
    # decide (18376129: checks on creation and every later read or write)
    problems = check_evidence_paths(a_out, allowed_dirs=REVIEW_EVIDENCE_DIRS)
    if problems:
        raise SystemExit(f"{what} refused: evidence path boundary: "
                         + "; ".join(problems))
    problems = review_store_problems(a_out)
    if problems:
        raise SystemExit(f"{what} refused: the evidence store holds what the "
                         "harness did not write: " + "; ".join(problems))
    spent = claimed_shard_ids(a_out)
    already = [m["shard_id"] for m in selected if m["shard_id"] in spent]
    if already:
        raise SystemExit(f"{what} refused: shard ID(s) already claimed, "
                         f"recorded, or installed under this evidence root: "
                         f"{already}; a claimed shard is never re-run")
    # every relationship among the artifacts already on disk is recomputed
    # before a new ruling is spent: a corrupt or forged evidence root never
    # hosts another command (Ari, room 255: recompute at status and review)
    corrupt = {sid: s["problems"] for sid, s in
               shard_states(out_root, a_out).items() if s["state"] == "CORRUPT"}
    if corrupt:
        raise SystemExit(f"{what} refused: evidence root is inconsistent: "
                         + "; ".join(f"{sid}: {', '.join(p)}"
                                     for sid, p in sorted(corrupt.items())))
    unfinalized = [c for c in command_states(a_out) if c["problems"]]
    if unfinalized:
        raise SystemExit(f"{what} refused: prior command(s) are not finalized "
                         "or not consistent: " + "; ".join(
                             f"ruling {c['ruling_id']}: {', '.join(c['problems'])}"
                             for c in unfinalized))
    reservation_file = os.path.join(a_out, RESERVATIONS_DIR,
                                    f"{REVIEW_RESERVATION_PREFIX}{ruling_id}.json")
    if os.path.lexists(reservation_file):
        raise SystemExit(f"{what} refused: ruling {ruling_id} is already "
                         f"reserved ({os.path.relpath(reservation_file, a_out)})"
                         "; a ruling authorizes exactly one review command")
    # hard stop for the WHOLE selection before any session exists
    preverify_selection(selected, out_root)
    cli_build = cli_version()
    # every directory the command writes exists as a real directory BEFORE
    # the reservation, so nothing that runs during the command can plant a
    # file at those names (isolated adversary on this head, finding 3b)
    for sub in REVIEW_EVIDENCE_DIRS:
        d = os.path.join(a_out, sub)
        try:
            canon.refuse_unless_real_dir(d, f"{sub} directory")
        except canon.PathBoundaryError as err:
            raise SystemExit(f"{what} refused: {err}")
        os.makedirs(d, exist_ok=True)
    policy = identity["auxiliary_model_policy"]
    command_attempt_id = str(uuid.uuid4())
    shards = [{"shard_id": m["shard_id"], "input_sha256": m["sha256"],
               "input_path": m["path"], "result": "NOT_RUN", "phase": None,
               "claim_path": None, "record_path": None, "record_sha256": None,
               "output_path": None, "output_sha256": None,
               "model_calls": 0, "cli_invocations": None, "error": None,
               "manifest_error": None}
              for m in selected]
    # every deterministic check has passed; from here the ruling is spent
    # whatever happens next, and every exit writes ONE terminal command
    # record that says what happened to every shard it named
    reserved_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    reservation_meta = {
        "artifact_version": "foundry-pass-2-review-reservation/experimental-v0.1",
        "purpose": "governed-review", "reserved_utc": reserved_utc,
        "command_attempt_id": command_attempt_id,
        "ruling_id": ruling_id, "head": head_of(identity),
        "identity_sha256": identity_sha,
        "model_id": MODEL, "ruled_model_id": ruled_model,
        "model_version_or_build": cli_build,
        "configuration_sha256": identity["configuration_sha256"],
        "environment_boundary_sha256": identity["environment_boundary_sha256"],
        "auxiliary_model_policy": policy,
        "shards": [{"shard_id": s["shard_id"], "input_sha256": s["input_sha256"]}
                   for s in shards],
        "call_ceiling": len(shards), "attempts_allowed": REVIEW_ATTEMPTS,
        "stopping_rule": ("one CLI invocation per shard call, in the order "
                          "named; the first shard that does not finish DONE "
                          "stops the command and every remaining shard is "
                          "NOT_RUN; a claimed shard is never re-run; the "
                          "ruling is spent by this reservation"),
        "bindings": expected,
    }
    outcome = {
        "artifact_version": "foundry-pass-2-review-command/experimental-v0.1",
        "purpose": "governed-review", "reviewer_role": "reviewer_a",
        "command_attempt_id": command_attempt_id,
        "ruling_id": ruling_id, "head": head_of(identity),
        "identity_sha256": identity_sha,
        "model_id": MODEL, "ruled_model_id": ruled_model,
        "model_version_or_build": cli_build,
        "configuration_sha256": identity["configuration_sha256"],
        "auxiliary_model_policy": policy,
        "reservation_path": os.path.relpath(reservation_file, a_out),
        "reservation_sha256": None,
        "started_utc": reserved_utc, "finished_utc": None,
        "call_ceiling": len(shards), "attempts_allowed": REVIEW_ATTEMPTS,
        "model_calls": 0, "cli_invocations": 0,
        "result": None, "phase": "reservation", "error": None,
        "shards": shards,
    }
    try:
        reservation = _reserve_exclusive(
            a_out, reservation_file, reservation_meta, what,
            subject=f"ruling {ruling_id}",
            tail="a new command needs a new maintainer ruling")
    except BaseException as err:  # noqa: B036
        if os.path.lexists(reservation_file):
            # the ruling is spent by existence (partial bytes or not) with
            # no session: the terminal record says so, every shard NOT_RUN
            # (isolated adversary on this head, finding 3a)
            try:
                outcome["reservation_sha256"] = canon.bytes_digest(
                    canon.read_regular_bytes(reservation_file))
            except Exception:  # noqa: BLE001
                outcome["reservation_sha256"] = None
            outcome["result"] = "FAIL"
            outcome["error"] = (f"reservation not durably written: "
                                f"{type(err).__name__}: {str(err)[:400]}")
            finalize_review_command(a_out, outcome)
        raise
    try:
        # nothing after the reservation runs outside these handlers: an
        # exception anywhere from here leaves T (second isolated pass,
        # finding 4: a signal between the reservation and the loop left
        # a spent ruling with no terminal record and no output)
        outcome["reservation_sha256"] = _sha(reservation)
        outcome["phase"] = "reserved"
        for entry, member in zip(shards, selected):
            outcome["phase"] = f"shard {member['shard_id']}"
            try:
                _review_one_shard(entry, member, out_root, a_out, session_factory,
                                  system_prompt, template, digests, schema,
                                  identity, outcome, what)
            finally:
                # the command's counts are accumulated on EVERY exit from
                # the shard, a propagating signal included: the terminal
                # record and the ledger line must never publish fewer
                # invocations than the shard record attests (isolated
                # adversary on this head, finding 4)
                outcome["model_calls"] += entry["model_calls"]
                if isinstance(entry["cli_invocations"], int):
                    outcome["cli_invocations"] += entry["cli_invocations"]
            if entry["result"] != "DONE":
                outcome["result"] = "FAIL"
                outcome["error"] = (f"{member['shard_id']}: {entry['result']} "
                                    f"in phase {entry['phase']}: {entry['error']}")[:800]
                break
            # the index is refreshed durably after every terminal shard exit
            # (18376129); the shard's record is already the truth, so a
            # failure here stops the command without touching that record
            try:
                write_run_record_manifest(a_out)
            except Exception as err:  # noqa: BLE001
                entry["manifest_error"] = f"{type(err).__name__}: {str(err)[:200]}"
                outcome["result"] = "FAIL"
                outcome["error"] = (f"manifest not rebuilt after "
                                    f"{member['shard_id']}: {entry['manifest_error']}")
                break
        else:
            outcome["result"] = "PASS"
        outcome["phase"] = "finalized"
    except BaseException as err:  # noqa: B036 - recorded, then propagated
        outcome["result"] = "FAIL"
        outcome["error"] = (outcome["error"] or
                            f"harness aborted during {outcome['phase']}: "
                            f"{type(err).__name__}: {str(err)[:400]}")
        if isinstance(err, SystemExit):
            # a SystemExit raised by a session or a seam is not this
            # command's verdict; the exit status is derived from the
            # terminal record, never from a foreign exit code (finding 9)
            raise SystemExit(f"review failed: {outcome['error']}") from None
        raise
    finally:
        projections_ok = finalize_review_command(a_out, outcome)
    raise SystemExit(0 if outcome["result"] == "PASS" and projections_ok else 1)


def head_of(identity):
    return identity["head"]


class _ObservedSession:
    """The session as review_shard sees it, plus the raw CLI result of its
    last call kept where the record can attest it (modelUsage, session id).
    Every attribute review_shard and invocation_accounting read is the
    inner session's own; nothing is invented here."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "last_result", None)
        object.__setattr__(self, "calls", 0)

    def run(self, prompt):
        object.__setattr__(self, "calls", self.calls + 1)
        result = self._inner.run(prompt)
        object.__setattr__(self, "last_result", result)
        return result

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _review_one_shard(entry, member, out_root, a_out, session_factory,
                      system_prompt, template, digests, schema, identity,
                      command, what):
    """One shard under the command: a fresh scratch directory and a fresh
    one-attempt session whose configuration must hash to what the identity
    binds; the claim installed immediately before the one call; the output
    installed with read-back; then the immutable shard record written LAST
    at every exit that follows the claim. Updates `entry` in place; returns
    nothing; propagates any BaseException after the record is written."""
    shard_id = member["shard_id"]
    shard_path = bound_shard_path(out_root, member)
    policy = identity["auxiliary_model_policy"]
    record = {
        "artifact_version": "foundry-pass-2-shard-attempt/experimental-v0.1",
        "purpose": "shard-review", "reviewer_role": "reviewer_a",
        "command_attempt_id": command["command_attempt_id"],
        "ruling_id": command["ruling_id"], "head": command["head"],
        "identity_sha256": command["identity_sha256"],
        "model_id": command["model_id"], "ruled_model_id": command["ruled_model_id"],
        "model_version_or_build": command["model_version_or_build"],
        "configuration_sha256": command["configuration_sha256"],
        "auxiliary_model_policy": policy,
        "auxiliary_model_violations": [],
        "observed_model_usage": None,
        "shard_id": shard_id, "input_path": member["path"],
        "input_sha256": member["sha256"],
        "reservation_path": command["reservation_path"],
        "claim_path": None, "claim_sha256": None,
        "started_utc": None, "phase": "session-construction",
        "result": None, "error": None,
        "attempts_allowed": REVIEW_ATTEMPTS,
        "model_calls": 0, "cli_invocations": None,
        "live_invocations_started": None,
        "invocation_accounting": "unavailable",
        "cli_invocation_log": [],
        "session_id": None, "num_turns": None,
        "prompt_sha256": None, "raw_response_sha256": None, "raw_response": None,
        "machine_corrections": None, "pre_call_record_verification": None,
        "completeness_check": None, "schema_report": None,
        "problems": None, "verdict": None,
        "output_path": None, "output_sha256": None, "output_byte_length": None,
    }
    entry["phase"] = record["phase"]
    cwd = tempfile.mkdtemp(prefix=f"foundry-reviewer-a-{shard_id}-")
    try:
        session = session_factory(system_prompt, cwd, REVIEW_ATTEMPTS)
    except BaseException as err:  # noqa: B036 - zero-call, no claim, reported
        entry.update(result="NOT_RUN", error=(
            f"session construction failed: {type(err).__name__}: "
            f"{str(err)[:300]}"))
        _rmtree_best_effort(cwd)
        if isinstance(err, Exception):
            return
        raise
    # the session must SAY what it allows and what it runs, and it must be
    # the configuration the identity binds; anything else is refused before
    # the claim, so the shard stays NOT_RUN and the command stops
    reason = None
    if getattr(session, "attempts", None) != REVIEW_ATTEMPTS:
        reason = (f"session reports attempts={getattr(session, 'attempts', None)!r}; "
                  f"the ruling allows exactly {REVIEW_ATTEMPTS}")
    elif not (callable(getattr(session, "command", None))
              and callable(getattr(session, "environment_boundary", None))
              and isinstance(getattr(session, "timeout", None), int)
              and not isinstance(getattr(session, "timeout", None), bool)
              and getattr(session, "timeout", 0) > 0):
        reason = ("session does not expose its command, environment boundary, "
                  "and a positive timeout")
    else:
        reason = _session_drift(session, identity)
    if reason:
        entry.update(result="NOT_RUN", error=reason)
        _rmtree_best_effort(cwd)
        return
    # the input bytes are read once, without following links, hashed, and
    # copied into this shard's private scratch directory; the call reads
    # the copy, so the digest the record attests is the digest of the bytes
    # the model was sent, not a manifest field (isolated adversary on this
    # head, finding 5)
    try:
        input_bytes = canon.read_regular_bytes(shard_path)
    except (OSError, canon.PathBoundaryError) as err:
        entry.update(result="NOT_RUN", error=(
            f"input unreadable at call time: {type(err).__name__}: {str(err)[:200]}"))
        _rmtree_best_effort(cwd)
        return
    input_sha = canon.bytes_digest(input_bytes)
    if input_sha != member["sha256"]:
        entry.update(result="NOT_RUN", error=(
            f"input digest drift since preverify: {input_sha} is not the bound "
            f"{member['sha256']}"))
        _rmtree_best_effort(cwd)
        return
    scratch_shard = os.path.join(cwd, "shard.json")
    fd = os.open(scratch_shard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        canon.write_all(fd, input_bytes, "scratch shard copy")
        os.fsync(fd)
    finally:
        os.close(fd)
    if canon.read_regular_bytes(scratch_shard) != input_bytes:
        entry.update(result="NOT_RUN", error="scratch shard copy does not hold "
                                              "the input bytes")
        _rmtree_best_effort(cwd)
        return
    record["input_sha256"] = input_sha
    # the claim: the shard is spent from here whatever happens next
    record["phase"] = entry["phase"] = "claim"
    claim_file = os.path.join(a_out, CLAIMS_DIR, f"{shard_id}.json")
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record["started_utc"] = started_utc
    claim_meta = {
        "artifact_version": "foundry-pass-2-shard-claim/experimental-v0.1",
        "purpose": "shard-review", "claimed_utc": started_utc,
        "command_attempt_id": command["command_attempt_id"],
        "ruling_id": command["ruling_id"], "head": command["head"],
        "identity_sha256": command["identity_sha256"],
        "shard_id": shard_id, "input_sha256": member["sha256"],
        "model_id": command["model_id"],
        "reservation_path": command["reservation_path"],
        "reservation_sha256": command["reservation_sha256"],
        "attempts_allowed": REVIEW_ATTEMPTS,
    }
    propagate = None
    try:
        try:
            claim = _reserve_exclusive(
                a_out, claim_file, claim_meta, what,
                subject=f"shard {shard_id}",
                tail="a claimed shard is never re-run")
        except AlreadyReserved as err:
            # another command claimed this shard between this command's
            # pre-check and its claim (Ari, room 266: two overlapping
            # commands past precheck; exactly one claim can win). Nothing
            # was created here, no call is made, no record is written under
            # the winner's shard; this command stops with the shard NOT_RUN
            entry.update(result="NOT_RUN", error=(
                f"claimed by another command before this one could claim it: "
                f"{str(err)[:300]}"))
            _rmtree_best_effort(cwd)
            return
        except BaseException as err:  # noqa: B036
            # the claim path may now exist (spent) or not (nothing spent);
            # existence decides, exactly as it does for refusal
            if os.path.lexists(claim_file):
                record["claim_path"] = os.path.relpath(claim_file, a_out)
                record["result"] = "FAIL"
                record["error"] = (f"claim not durably written: "
                                   f"{type(err).__name__}: {str(err)[:300]}")
                propagate = err
                raise _ShardStop()
            entry.update(result="NOT_RUN", error=(
                f"claim could not be created: {type(err).__name__}: "
                f"{str(err)[:300]}"))
            if isinstance(err, Exception):
                return
            raise
        record["claim_path"] = os.path.relpath(claim, a_out)
        record["claim_sha256"] = _sha(claim)
        entry["claim_path"] = record["claim_path"]
        record["phase"] = entry["phase"] = "invocation"
        observed = _ObservedSession(session)
        total_before = getattr(session, "total_invocations", None)
        total_before = total_before if isinstance(total_before, int) and \
            not isinstance(total_before, bool) else None
        review_record = None
        try:
            review_record = reviewer.review_shard(
                observed, template, digests, scratch_shard,
                member["artifact_ids"], schema_validator, schema)
        except reviewer.ReviewerError as err:
            record["result"] = "FAIL"
            record["error"] = str(err)[:500]
            if observed.last_result is not None:
                record["phase"] = "validation"
        except BaseException as err:  # noqa: B036 - a spent call is recorded
            record["result"] = "FAIL"
            record["error"] = (f"harness aborted: {type(err).__name__}: "
                               f"{str(err)[:400]}")
            if observed.last_result is not None:
                record["phase"] = "validation"
            if not isinstance(err, Exception):
                # an interrupt keeps its meaning after the record; any other
                # exception is the shard's failure and the command's stop
                propagate = err
        # the live accounting, from the session in hand, never from disk
        total_after = getattr(session, "total_invocations", None)
        if total_before is not None and isinstance(total_after, int) and \
                not isinstance(total_after, bool):
            invocations = total_after - total_before
            accounting = "session-reported (cumulative total delta)"
        else:
            live = getattr(session, "last_invocations", None)
            invocations = live if isinstance(live, int) and \
                not isinstance(live, bool) else None
            accounting = ("session-reported (per-call count)"
                          if invocations is not None else "unavailable")
        if isinstance(invocations, int) and invocations < 0:
            invocations = None
            accounting = "unavailable (session reported a count that went backwards)"
        record["cli_invocations"] = invocations
        record["live_invocations_started"] = invocations
        record["invocation_accounting"] = accounting
        record["cli_invocation_log"] = list(getattr(session, "last_invocation_log", []) or [])
        record["model_calls"] = observed.calls
        last = observed.last_result
        if isinstance(last, dict):
            record["session_id"] = last.get("session_id")
            record["num_turns"] = last.get("num_turns")
            record["raw_response"] = last.get("result", "")
            record["raw_response_sha256"] = canon.content_digest(last.get("result", ""))
            usage = observed_model_usage({"transcripts": [
                {"probe_id": shard_id, "result": last}]})
            record["observed_model_usage"] = usage
        else:
            usage = []
        if review_record is not None:
            for key in ("prompt_sha256", "session_id", "num_turns",
                        "machine_corrections", "pre_call_record_verification",
                        "completeness_check", "schema_report", "problems",
                        "verdict", "raw_response_sha256"):
                if key in review_record:
                    record[key] = review_record[key] if key != "prompt_sha256" \
                        else review_record["task_prompt_sha256"]
        if record["result"] is None:
            # the call returned: the ruling's sentence is checked against
            # what the session and the CLI reported before any output is
            # installed (binding parity: counting is not enforcement)
            record["phase"] = "policy"
            violations = aux_policy_violations(usage, command["model_id"], policy) \
                if usage else []
            record["auxiliary_model_violations"] = violations
            drift = _session_drift(session, identity)
            scratch_now = (canon.bytes_digest(canon.read_regular_bytes(scratch_shard))
                           if canon.is_regular(scratch_shard) else None)
            if drift:
                # the configuration is what it was when checked, or the
                # shard is not bound to the identity (finding 8)
                record["result"] = "FAIL"
                record["error"] = f"after the call, {drift}"
            elif scratch_now != input_sha:
                record["result"] = "FAIL"
                record["error"] = ("the scratch input was altered during the "
                                   f"call: {scratch_now} is not {input_sha}")
            elif not isinstance(invocations, int):
                record["result"] = "FAIL"
                record["error"] = ("invocation count unavailable: the session did "
                                   "not report a valid CLI invocation count "
                                   f"({accounting})")
            elif invocations != REVIEW_ATTEMPTS:
                record["result"] = "FAIL"
                record["error"] = (f"invocation accounting does not match the "
                                   f"ruling: {invocations} CLI invocation(s) for "
                                   f"1 shard call; exactly {REVIEW_ATTEMPTS} allowed")
            elif not usage or not usage[0]["model_usage_reported"]:
                record["result"] = "FAIL"
                record["error"] = ("auxiliary model policy could not be checked: "
                                   "no modelUsage reported for the shard call")
            elif violations:
                record["result"] = "FAIL"
                record["error"] = ("model usage violates the bound policy: "
                                   + "; ".join(violations))[:500]
            elif review_record.get("verdict") != "fixed":
                record["phase"] = "validation"
                record["result"] = "FAIL"
                record["error"] = (f"verdict {review_record.get('verdict')!r}: "
                                   f"{review_record.get('problems')}")[:500]
        if record["result"] is None:
            record["phase"] = "install"
            output_file = os.path.join(a_out, OUTPUTS_DIR, f"{shard_id}.json")
            try:
                sha, length = install_output_readback(output_file,
                                                      review_record["output"])
            except SystemExit as err:
                record["result"] = "FAIL"
                record["error"] = f"output not installed: {err.code}"[:500]
            except BaseException as err:  # noqa: B036
                record["result"] = "FAIL"
                record["error"] = (f"output not installed: {type(err).__name__}: "
                                   f"{str(err)[:400]}")
                if not isinstance(err, Exception):
                    propagate = err
            else:
                record["output_path"] = os.path.relpath(output_file, a_out)
                record["output_sha256"] = sha
                record["output_byte_length"] = length
                record["result"] = "DONE"
                record["phase"] = "finalized"
        raise _ShardStop()
    except _ShardStop:
        pass
    finally:
        _rmtree_best_effort(cwd)
        if record["claim_path"] is not None:
            # the record is written LAST, after the output, at every exit
            # that follows the claim; a claim with no record is a spent,
            # unattested shard that status reports and review refuses
            entry.update(result=record["result"], phase=record["phase"],
                         error=record["error"], model_calls=record["model_calls"],
                         cli_invocations=record["cli_invocations"],
                         output_path=record["output_path"],
                         output_sha256=record["output_sha256"])
            try:
                (rec_sha, rec_path), interrupted = _write_shard_record_once(
                    a_out, record)
            except BaseException as err:  # noqa: B036
                entry.update(result="UNATTESTED", error=(
                    f"shard record not written: {type(err).__name__}: "
                    f"{str(err)[:300]}"))
                if propagate is None:
                    raise
            else:
                entry.update(record_path=os.path.relpath(rec_path, a_out),
                             record_sha256=rec_sha)
                if interrupted is not None and propagate is None:
                    # the record is on disk; the signal that interrupted
                    # its write still stops the command
                    propagate = interrupted
    if propagate is not None:
        raise propagate


class _ShardStop(Exception):
    """Internal: leave the shard body; the finally clause writes the record."""


def _session_drift(session, identity):
    """Why this session is not the one the identity binds, or None. Read
    before the claim and again after the call, from the session object in
    hand (isolated adversary on this head, finding 8: the command line was
    read once, and the model attribute never).

    Honest limit: the harness can only compare what the session object
    SAYS about itself; a session that reports the bound command on both
    reads while running something else is outside what any caller can
    observe. The session class the identity binds is the real
    IsolatedSession, whose command() is what it runs; the invocation and
    model-usage checks are the observations that do not depend on the
    session's word."""
    if getattr(session, "model", None) != identity["model_id"]:
        return (f"session model {getattr(session, 'model', None)!r} is not the "
                f"bound {identity['model_id']!r}")
    try:
        configuration = {"command": list(session.command())[:-1] + ["<system prompt>"],
                         "timeout_s": session.timeout}
        boundary = session.environment_boundary()
    except Exception as err:  # noqa: BLE001
        return f"session configuration unreadable: {type(err).__name__}"
    if canon.content_digest(configuration) != identity["configuration_sha256"]:
        return "session configuration differs from the one the identity binds"
    if canon.content_digest(boundary) != identity["environment_boundary_sha256"]:
        return "session environment boundary differs from the one the identity binds"
    return None


def _rmtree_best_effort(path):
    try:
        shutil.rmtree(path)
    except OSError:
        pass


def _write_shard_record_once(a_out, record):
    """The immutable shard record, content-addressed under the shard's own
    name (run-records/<shard_id>.<sha256>.json); an interrupt inside the
    write is retried once with the interruption named, then propagated."""
    directory = os.path.join(a_out, RUN_RECORDS_DIR)
    prefix = f"{record['shard_id']}."
    return _write_record_once(directory, prefix, {
        "shard_id": record["shard_id"],
        "command_attempt_id": record["command_attempt_id"]}, record)


def _write_record_once(directory, prefix, fields, record):
    """Returns ((sha, path), interruption). A record for this key is never
    written twice: one that already exists is returned; one whose write
    raised after the bytes landed is returned with the exception; one whose
    write was interrupted before the bytes landed is retried once with the
    interruption named, and that exception is returned beside the retried
    record so the caller can still honour the signal; if the retry fails
    too, the original exception propagates."""
    existing = _existing_record(directory, prefix, fields)
    if existing is not None:
        return existing, None
    try:
        return write_review_record(directory, prefix, record), None
    except BaseException as err:  # noqa: B036 - the record is the evidence
        existing = _existing_record(directory, prefix, fields)
        if existing is not None:
            return existing, err
        try:
            return write_review_record(directory, prefix, dict(
                record, record_write_interrupted=f"{type(err).__name__}: "
                                                 f"{str(err)[:200]}")), err
        except BaseException:  # noqa: B036, BLE001 - the first failure is reported
            raise err


def _existing_record(directory, prefix, fields):
    """The (sha, path) of the one record under `directory` whose name has
    `prefix` and whose content carries every field in `fields`; None if
    there is none. Read without following links; unreadable files do not
    match."""
    if not canon.is_real_dir(directory):
        return None
    for name in sorted(os.listdir(directory)):
        if name.startswith(prefix) and name.endswith(".json"):
            try:
                rec = canon.load_json_regular(os.path.join(directory, name))
            except Exception:  # noqa: BLE001
                continue
            if all(rec.get(k) == v for k, v in fields.items()):
                return name[len(prefix):-5], os.path.join(directory, name)
    return None


def write_review_record(directory, prefix, record):
    """Immutable, content-addressed record for the review path (shard and
    command records), written durably: temporary file, write_all, fsync,
    link into place (never replacing an existing name), directory fsync.
    Its own seam so tests can inject failures and interrupts."""
    try:
        canon.refuse_unless_real_dir(directory, "record directory")
    except canon.PathBoundaryError as err:
        raise SystemExit(f"review refused: {err}")
    os.makedirs(directory, exist_ok=True)
    data = canon.canonical_bytes(record)
    rec_sha = canon.bytes_digest(data)
    rec_path = os.path.join(directory, f"{prefix}{rec_sha}.json")
    # the temporary lives in the evidence root, never in the indexed
    # directory, so a crash leaves no pseudo-member behind (finding 12)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-record-", suffix=".json",
                               dir=os.path.dirname(directory))
    try:
        canon.write_all(fd, data, "review record")
        os.fsync(fd)
        if os.fstat(fd).st_size != len(data):
            raise canon.ShortWriteError("review record: size on disk differs "
                                        "from the payload after fsync")
        os.fchmod(fd, 0o644)
        os.close(fd)
        fd = None
        os_link(tmp, rec_path)   # FileExistsError: the record already exists
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    dfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return rec_sha, rec_path


def install_output_readback(path, obj):
    """Install one shard output exactly once, verified from the same
    descriptor that wrote it (18376129: output installed atomically with
    read-back, then the shard record). The same sequence as the identity
    install, kept separate so the identity primitive stays byte-identical:
    refuse if anything exists at `path`; canonical bytes to a same-directory
    temporary file through write_all; fsync; fstat size equal to the
    payload; every byte read back from the same descriptor with pread and
    equal to the payload; digest from the bytes read back; link() into
    place, never replacing; directory fsync; the installed path read once
    more without following links and equal to the payload. Returns
    (sha256, byte_length)."""
    directory = os.path.dirname(path) or "."
    try:
        canon.refuse_unless_real_dir(directory, "outputs directory")
    except canon.PathBoundaryError as err:
        raise SystemExit(f"review output refused: {err}")
    os.makedirs(directory, exist_ok=True)
    if os.path.lexists(path):
        raise SystemExit(f"review output refused: {os.path.basename(path)} "
                         "already exists; an output is never overwritten")
    data = canon.canonical_bytes(obj)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-output-", suffix=".json",
                               dir=os.path.dirname(directory))
    try:
        canon.write_all(fd, data, "output temporary file")
        os.fsync(fd)
        on_disk = os.fstat(fd).st_size
        if on_disk != len(data):
            raise canon.ShortWriteError(
                f"output temporary file: {on_disk} byte(s) on disk for a "
                f"{len(data)} byte payload after fsync; refusing to install")
        back = bytearray()
        while len(back) < len(data):
            chunk = os.pread(fd, min(65536, len(data) - len(back)), len(back))
            if not chunk:
                raise canon.ShortWriteError(
                    f"output temporary file: read back ended after "
                    f"{len(back)} of {len(data)} byte(s); refusing to install")
            back += chunk
        if os.pread(fd, 1, len(data)) != b"":
            raise canon.ShortWriteError(
                "output temporary file: more bytes on disk than the payload; "
                "refusing to install")
        if bytes(back) != data:
            raise canon.ShortWriteError(
                "output temporary file: bytes read back from the same "
                "descriptor differ from the payload; refusing to install")
        digest = canon.bytes_digest(bytes(back))
        os.fchmod(fd, 0o644)
        os.close(fd)
        fd = None
        try:
            os_link(tmp, path)
        except FileExistsError:
            raise SystemExit(f"review output refused: {os.path.basename(path)} "
                             "appeared during install and was not overwritten")
        except OSError as err:
            raise SystemExit(f"review output refused: {os.path.basename(path)} "
                             f"could not be installed by link ({err}); nothing "
                             "was installed")
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    dfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    try:
        installed = canon.read_regular_bytes(path)
    except (OSError, canon.PathBoundaryError) as err:
        installed = None
        detail = f"{type(err).__name__}: {err}"
    else:
        detail = "bytes differ"
    if installed != data:
        # the bytes are moved OUT of the outputs directory, which the gate
        # reads whole, into the evidence root under a name the store check
        # refuses on (second isolated pass, finding 1: a quarantined file
        # inside outputs/ was indexed as a fixed output and consumed by the
        # gate for a shard that was never reviewed)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        n = 0
        while True:
            quarantine = os.path.join(
                os.path.dirname(directory),
                f"REFUSED-output-{os.path.basename(path)[:-5]}-{stamp}-{n}.json")
            if not os.path.lexists(quarantine):
                break
            n += 1
        moved = None
        if os.path.lexists(path):
            try:
                os.rename(path, quarantine)
                moved = os.path.basename(quarantine)
            except OSError:
                moved = None
        raise SystemExit(f"review output refused: {os.path.basename(path)} on "
                         f"disk does not hold the verified bytes after install "
                         f"({detail}); "
                         + (f"moved to {moved}" if moved else
                            "nothing was moved (the path was absent or the "
                            "move failed)"))
    return digest, len(data)


def finalize_review_command(a_out, outcome):
    """The one terminal command record for this command, the ledger
    projection, the rebuilt manifest, and the ledger line. Runs on every
    post-reservation exit. Never written twice for one command attempt;
    an interrupt inside the write is retried once with the interruption
    named, then propagated. The manifest is an index: its failure is
    reported on the line, never allowed to mask the record."""
    outcome["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if outcome["result"] is None:
        outcome["result"] = "FAIL"
    directory = os.path.join(a_out, COMMAND_RECORDS_DIR)
    prefix = f"{outcome['command_attempt_id']}."
    try:
        (rec_sha, _rec_path), interrupted = _write_record_once(
            directory, prefix, {"command_attempt_id": outcome["command_attempt_id"]},
            outcome)
    except BaseException as err:  # noqa: B036 - loud, then propagated
        # nothing can be projected from a record that is not on disk; the
        # operator is told in words, and status reports the reservation as
        # unfinalized until it is (finding 3b)
        print("TERMINAL COMMAND RECORD NOT WRITTEN for command "
              f"{outcome['command_attempt_id']} (ruling {outcome['ruling_id']}): "
              f"{type(err).__name__}: {str(err)[:300]}")
        for s in outcome["shards"]:
            print(f"  {s['shard_id']} {s['result']}"
                  + (f" record {s['record_sha256']}" if s["record_sha256"] else ""))
        raise
    counts = {"DONE": 0, "FAIL": 0, "NOT_RUN": 0, "UNATTESTED": 0}
    for s in outcome["shards"]:
        counts[s["result"]] = counts.get(s["result"], 0) + 1
    ledger_note = ""
    try:
        _append_review_ledger(a_out, outcome, rec_sha)
    except BaseException as err:  # noqa: B036 - a projection; T is on disk
        # the ledger is a projection of T: its failure is said on the line
        # and in the exit status, and never hides T or the line itself
        # (isolated adversary on this head, finding 10)
        ledger_note = f" | ledger NOT appended ({type(err).__name__})"
        if not isinstance(err, Exception):
            _print_review_ledger_line(outcome, rec_sha, counts, ledger_note
                                      + " (interrupted; terminal record is on disk)")
            raise
    manifest_note = ""
    try:
        write_run_record_manifest(a_out)
    except BaseException as err:  # noqa: B036 - an index, reported not masked
        manifest_note = f" | manifest NOT rebuilt ({type(err).__name__})"
        if not isinstance(err, Exception):
            _print_review_ledger_line(outcome, rec_sha, counts, ledger_note
                                      + manifest_note
                                      + " (interrupted; terminal record is on disk)")
            raise
    if manifest_note or any(s.get("manifest_error") for s in outcome["shards"]):
        manifest_note = manifest_note or " | manifest NOT rebuilt after a shard"
    manifest_note = ledger_note + manifest_note
    _print_review_ledger_line(outcome, rec_sha, counts, manifest_note)
    if interrupted is not None:
        # the record and the ledger are on disk; the signal that interrupted
        # the record write keeps its meaning
        raise interrupted
    return manifest_note == ""


def _print_review_ledger_line(outcome, rec_sha, counts, manifest_note):
    print("REVIEW LEDGER LINE:")
    print(f"head {outcome['head']} | ruling {outcome['ruling_id']} | model "
          f"{outcome['model_id']} | identity {outcome['identity_sha256']} | "
          f"command {outcome['command_attempt_id']} | shards "
          f"{len(outcome['shards'])} | done {counts['DONE']} | failed "
          f"{counts['FAIL']} | unattested {counts['UNATTESTED']} | not-run "
          f"{counts['NOT_RUN']} | calls {outcome['model_calls']} | invocations "
          f"{outcome['cli_invocations']} (allowed {outcome['attempts_allowed']} "
          f"per call, ceiling {outcome['call_ceiling']}) | result "
          f"{outcome['result']} | record {rec_sha} | reservation "
          f"{outcome['reservation_path']}{manifest_note}")
    for s in outcome["shards"]:
        print(f"  {s['shard_id']} {s['result']}"
              + (f" output {s['output_sha256']}" if s["output_sha256"] else "")
              + (f" record {s['record_sha256']}" if s["record_sha256"] else "")
              + (f" ({s['phase']}: {s['error']})" if s["error"] else ""))
    if outcome["error"]:
        print("failure:", outcome["error"])


def _append_review_ledger(a_out, outcome, rec_sha):
    append_ledger(a_out, {
        "command_attempt_id": outcome["command_attempt_id"],
        "head": outcome["head"], "ruling_id": outcome["ruling_id"],
        "identity_sha256": outcome["identity_sha256"],
        "model": outcome["model_id"], "result": outcome["result"],
        "phase": outcome["phase"], "shards": [
            {"shard_id": s["shard_id"], "result": s["result"],
             "record_sha256": s["record_sha256"],
             "output_sha256": s["output_sha256"]} for s in outcome["shards"]],
        "model_calls": outcome["model_calls"],
        "cli_invocations": outcome["cli_invocations"],
        "call_ceiling": outcome["call_ceiling"],
        "attempts_allowed": outcome["attempts_allowed"],
        "reservation_path": outcome["reservation_path"],
        "record_sha256": rec_sha,
        "started_utc": outcome["started_utc"],
        "finished_utc": outcome["finished_utc"]},
        REVIEW_LEDGER, "foundry-pass-2-review-ledger/experimental-v0.1")


IDENTITY_BOUND_FIELDS = (
    "head", "ruling_id", "ruled_model_id", "model_id",
    "model_version_or_build", "harness_sha256", "parser_sha256",
    "tool_allowlist_sha256", "settings_sources_sha256",
    "system_prompt_sha256", "task_prompt_template_sha256",
    "output_schema_sha256", "configuration_sha256", "configuration",
    "environment_boundary_sha256", "environment_boundary",
    "leak_probe_transcript_sha256", "leak_probe_evidence_path",
    "binding_attempt_id", "reservation_path", "reservation_sha256",
    "auxiliary_model_policy", "observed_model_usage", "bindings",
    "reviewer_role", "binding_attempts_allowed", "leak_probes",
    "leak_probes_sha256", "session_ids_sha256",
)
# fields the identity must carry with the same value as its binding attempt
# record (the record is found by the identity's attempt id, verified against
# its own name, and must attest the identity's digest; the identity's copies
# are then held to it, so an edited identity cannot publish one thing while
# the record says another; isolated adversary on this head, finding 1)
IDENTITY_RECORD_FIELDS = (
    ("head", "head"), ("ruling_id", "ruling_id"),
    ("reviewer_role", "reviewer_role"),
    ("binding_attempts_allowed", "attempts_allowed"),
    ("leak_probes_sha256", "leak_probes_sha256"),
    ("session_ids_sha256", "session_ids_sha256"),
    ("ruled_model_id", "ruled_model_id"), ("model_id", "model_id"),
    ("model_version_or_build", "model_version_or_build"),
    ("harness_sha256", "harness_sha256"),
    ("system_prompt_sha256", "system_prompt_sha256"),
    ("task_prompt_template_sha256", "task_prompt_template_sha256"),
    ("output_schema_sha256", "output_schema_sha256"),
    ("leak_probe_transcript_sha256", "evidence_sha256"),
    ("leak_probe_evidence_path", "evidence_path"),
    ("binding_attempt_id", "attempt_id"),
    ("reservation_path", "reservation_path"),
    ("reservation_sha256", "reservation_sha256"),
    ("auxiliary_model_policy", "auxiliary_model_policy"),
    ("observed_model_usage", "observed_model_usage"),
    ("bindings", "bindings"),
)


def binding_record_for(a_out, attempt_id):
    """The one binding attempt record naming `attempt_id`, every record
    under a_out verified against its own content-addressed name first.
    Zero or several records for the attempt is a refusal."""
    matches = []
    for name in sorted(os.listdir(a_out)):
        if not (name.startswith(BINDING_RECORD_PREFIX) and name.endswith(".json")):
            continue
        path = os.path.join(a_out, name)
        if not canon.is_regular(path):
            raise SystemExit(f"review refused: binding attempt record {name} is "
                             "not a regular file")
        data = canon.read_regular_bytes(path)
        if canon.bytes_digest(data) != name[len(BINDING_RECORD_PREFIX):-5]:
            raise SystemExit(f"review refused: binding attempt record {name} "
                             "does not hash to its name; it has been altered")
        rec = json.loads(data.decode("utf-8"))
        if rec.get("attempt_id") == attempt_id:
            matches.append(rec)
    if len(matches) != 1:
        raise SystemExit(f"review refused: {len(matches)} binding attempt "
                         f"record(s) name attempt {attempt_id}; exactly one "
                         "is required")
    return matches[0]


def enforce_bound_identity(identity, a_out, system_prompt, identity_sha):
    """Review-time enforcement of the bound head and configuration
    (authorization 18371886; Ari's scope: binding parity alone would not
    prevent later code drift). Before any real shard session: the tree
    must sit at the identity's exact head and be clean; the harness bytes,
    the reviewer model, and the CLI build must be the ones the identity
    names; the system prompt and task template files must hash to what
    the identity binds; the session configuration and environment boundary
    recomputed from the real session class must hash to what the identity
    binds, and so must the identity's published copies; the probe evidence
    must be on disk with its digest; the binding attempt record named by
    the identity's attempt id must be on disk, hash to its name, say PASS,
    attest this identity's exact digest, and agree with the identity on
    every shared field; the reservation must be on disk with its digest.
    Anything else refuses before any session."""
    missing = [f for f in IDENTITY_BOUND_FIELDS
               if f not in identity or identity[f] in (None, "")]
    if missing:
        raise SystemExit("review refused: identity record lacks bound fields "
                         f"{missing}; rebind under a binding ruling")
    head, clean = git_head("review")
    if head != identity["head"]:
        raise SystemExit(f"review refused: tree is at {head}; the identity was "
                         f"bound at {identity['head']}; rebind at this head")
    if not clean:
        raise SystemExit(f"review refused: working tree is not clean at {head}; "
                         "the identity binds exact bytes")
    harness = _sha(os.path.join(PASS2, "engine", "reviewer.py"))
    if harness != identity["harness_sha256"]:
        raise SystemExit("review refused: engine/reviewer.py hashes to "
                         f"{harness}; the identity binds "
                         f"{identity['harness_sha256']}; rebind")
    for field, name in (("system_prompt_sha256", "reviewer-system-prompt-v0.1.md"),
                        ("task_prompt_template_sha256",
                         "reviewer-task-template-v0.1.md")):
        actual = _sha(os.path.join(ARI, name))
        if actual != identity[field]:
            raise SystemExit(f"review refused: {name} hashes to {actual}; the "
                             f"identity binds {identity[field]}; rebind")
    if MODEL != identity["model_id"]:
        raise SystemExit(f"review refused: the harness would run {MODEL!r}; "
                         f"the identity binds {identity['model_id']!r}")
    build = cli_version()
    if build != identity["model_version_or_build"]:
        raise SystemExit(f"review refused: CLI build is {build!r}; the identity "
                         f"binds {identity['model_version_or_build']!r}; rebind")
    probe = reviewer.IsolatedSession(MODEL, system_prompt, "")
    configuration = {"command": probe.command()[:-1] + ["<system prompt>"],
                     "timeout_s": probe.timeout}
    if canon.content_digest(configuration) != identity["configuration_sha256"]:
        raise SystemExit("review refused: session configuration differs from "
                         "the one the identity binds; rebind")
    if canon.content_digest(probe.environment_boundary()) != \
            identity["environment_boundary_sha256"]:
        raise SystemExit("review refused: environment boundary differs from "
                         "the one the identity binds; rebind")
    evidence = os.path.join(a_out, os.path.basename(
        identity["leak_probe_evidence_path"]))
    if not canon.is_regular(evidence) or \
            canon.bytes_digest(canon.read_regular_bytes(evidence)) != \
            identity["leak_probe_transcript_sha256"]:
        raise SystemExit("review refused: the probe evidence the identity "
                         "names is absent or altered")
    # the identity's account of its own attempt is recomputed from the
    # transcript just verified by digest, never trusted from the pair of
    # artifacts alone (pass three, finding 2)
    transcript = json.loads(canon.read_regular_bytes(evidence).decode("utf-8"))
    if transcript.get("attempt_id") != identity["binding_attempt_id"]:
        raise SystemExit("review refused: the identity names attempt "
                         f"{identity['binding_attempt_id']}; the probe evidence "
                         f"it names records attempt {transcript.get('attempt_id')}")
    if transcript.get("preflight_result") != "PASS":
        raise SystemExit("review refused: the probe evidence the identity names "
                         "is not a passed preflight")
    if canon.content_digest(transcript.get("records", [])) != identity["leak_probes_sha256"]:
        raise SystemExit("review refused: the identity's leak_probes_sha256 does "
                         "not match the verified probe evidence")
    if canon.content_digest([(t.get("result") or {}).get("session_id")
                             for t in transcript.get("transcripts", [])]) != \
            identity["session_ids_sha256"]:
        raise SystemExit("review refused: the identity's session_ids_sha256 does "
                         "not match the verified probe evidence")
    policy = identity["auxiliary_model_policy"]
    if not isinstance(policy, dict) or policy.get("policy") not in ("reject", "accept") or (
            policy.get("policy") == "accept" and not (
                isinstance(policy.get("auxiliary_model"), str)
                and MODEL_ID_RE.fullmatch(policy["auxiliary_model"]))):
        raise SystemExit("review refused: the identity's auxiliary model policy "
                         "is malformed; rebind")
    recomputed_usage = observed_model_usage(transcript)
    if recomputed_usage != identity["observed_model_usage"]:
        raise SystemExit("review refused: the identity's observed_model_usage "
                         "does not match the verified probe evidence")
    if aux_policy_violations(recomputed_usage, identity["model_id"],
                             identity["auxiliary_model_policy"]) or \
            any(not u["model_usage_reported"] for u in recomputed_usage):
        raise SystemExit("review refused: the verified probe evidence violates "
                         "the auxiliary model policy the identity carries")
    record = binding_record_for(a_out, identity["binding_attempt_id"])
    if record.get("result") != "PASS" or record.get("purpose") != "identity-binding":
        raise SystemExit("review refused: the binding attempt record for this "
                         "identity is not a passed identity-binding attempt")
    if record.get("identity_sha256") != identity_sha:
        raise SystemExit("review refused: the binding attempt record attests "
                         f"identity {record.get('identity_sha256')}; the "
                         f"identity on disk hashes to {identity_sha}; the "
                         "identity has been edited or replaced; rebind")
    for identity_field, record_field in IDENTITY_RECORD_FIELDS:
        if identity.get(identity_field) != record.get(record_field):
            raise SystemExit(f"review refused: identity {identity_field} does "
                             "not match the binding attempt record; the "
                             "identity has been edited; rebind")
    # what the identity publishes in clear must be what its digests bind
    if canon.content_digest(identity["configuration"]) != \
            identity["configuration_sha256"]:
        raise SystemExit("review refused: the identity's published "
                         "configuration does not hash to its "
                         "configuration_sha256; rebind")
    if canon.content_digest(identity["environment_boundary"]) != \
            identity["environment_boundary_sha256"]:
        raise SystemExit("review refused: the identity's published environment "
                         "boundary does not hash to its "
                         "environment_boundary_sha256; rebind")
    if identity["parser_sha256"] != harness or \
            identity["tool_allowlist_sha256"] != canon.content_digest([]) or \
            identity["settings_sources_sha256"] != canon.content_digest(""):
        raise SystemExit("review refused: parser, tool allowlist, or settings "
                         "sources digest differs from the bound harness; rebind")
    if identity["ruled_model_id"] != identity["model_id"]:
        raise SystemExit("review refused: the identity's ruled model and bound "
                         "model differ; rebind")
    if canon.content_digest(identity["leak_probes"]) != identity["leak_probes_sha256"]:
        raise SystemExit("review refused: the identity's published leak probe "
                         "records do not hash to its leak_probes_sha256; rebind")
    if identity["binding_attempts_allowed"] != BINDING_ATTEMPTS or \
            identity["reviewer_role"] != "reviewer_a":
        raise SystemExit("review refused: the identity's attempt budget or "
                         "role is not the one this harness binds; rebind")
    # the reservation the identity names must still be on disk, unchanged
    # (isolated adversary on this head, finding 2)
    reservation = os.path.join(a_out, os.path.basename(os.path.dirname(
        identity["reservation_path"])), os.path.basename(identity["reservation_path"]))
    if not canon.is_regular(reservation) or \
            canon.bytes_digest(canon.read_regular_bytes(reservation)) != \
            identity["reservation_sha256"]:
        raise SystemExit("review refused: the head reservation the identity "
                         "names is absent or altered")

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


def reservation_path(q_out, head, what="qualification"):
    if not valid_head(head):
        raise SystemExit(f"{what} refused: {head[:60]!r} is not a "
                         "40-hex commit sha (adversary F3: a non-sha head "
                         "could name a path outside the evidence root)")
    return os.path.join(q_out, RESERVATIONS_DIR, f"{head}.json")


def spent_head_reasons(q_out, head, record_prefix=QUALIFY_RECORD_PREFIX,
                       ledger_name=QUALIFY_LEDGER, what="qualification"):
    """Every durable trace that this exact head has already been given to
    qualify(), in authority order: (1) the pre-call reservation, (2) any
    immutable attempt record, (3) the ledger projection. Any one of them
    is sufficient to refuse. The ledger alone was the sole refusal source
    before this (Ari, 18321030, blocking finding 2): a failed ledger write
    after the model call left the head absent from the only place refusal
    looked, and a second call spent a second invocation."""
    reasons = []
    res = reservation_path(q_out, head, what)
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
            if name.startswith(record_prefix) and name.endswith(".json"):
                try:
                    rec = canon.load_json_regular(os.path.join(q_out, name))
                except Exception:  # noqa: BLE001 - unreadable records still count
                    rec = {"head": None}
                if rec.get("head") == head or rec.get("head") is None:
                    records.append((name, rec.get("result", "unknown")))
    if records:
        reasons.append(f"{len(records)} attempt record(s) ("
                       + ", ".join(f"{n} {r}" for n, r in records) + ")")
    ledger = os.path.join(q_out, ledger_name)
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


def refuse_if_spent(q_out, head, record_prefix=QUALIFY_RECORD_PREFIX,
                    ledger_name=QUALIFY_LEDGER, what="qualification"):
    """One attempt per exact commit, enforced against every durable trace,
    BEFORE any session is created or model call made."""
    reasons = spent_head_reasons(q_out, head, record_prefix, ledger_name, what)
    if reasons:
        raise SystemExit(
            f"{what} refused: head {head} is spent: "
            + "; ".join(reasons) + "; a new attempt needs a new exact commit")


def reserve_head(q_out, head, meta, artifact_version=
                 "foundry-pass-2-qualification-reservation/experimental-v0.1",
                 what="qualification"):
    """Exclusive, durable reservation of this exact head, written after
    every deterministic input check has passed and BEFORE any session
    exists. Exclusive create (O_EXCL) makes two concurrent calls resolve
    to exactly one holder; fsync on the file and its directory makes the
    reservation survive a crash before any later write. The reservation
    is authoritative for refusal even if the attempt record or the ledger
    is never written: a reserved head with no attempt record is a spent
    head by design (it may have reached the model), and needs a new
    commit. Never modified after creation."""
    path = reservation_path(q_out, head, what)
    record = dict(meta, artifact_version=artifact_version, head=head)
    return _reserve_exclusive(q_out, path, record, what, subject=f"head {head}",
                              tail="a new attempt needs a new exact commit")


class AlreadyReserved(SystemExit):
    """The exclusive create found the name taken: nothing was created by
    this caller. A SystemExit for every existing caller; the review path
    tells it apart from a write failure after the create (a racing command
    that lost a shard claim must not record the winner's shard as its own)."""


def _reserve_exclusive(q_out, path, record, what, subject, tail):
    """The exclusive durable create behind reserve_head, shared verbatim by
    the review path's command reservation (keyed by ruling ID) and shard
    claims (keyed by shard ID): O_EXCL create, write_all, fsync, fstat size
    check, directory fsync; on any failure after the create the object is
    left in place and reported as spent. `subject` and `tail` only shape
    the refusal wording."""
    try:
        canon.refuse_unless_real_dir(os.path.dirname(path),
                                     f"{os.path.basename(os.path.dirname(path))} directory")
    except canon.PathBoundaryError as err:
        raise SystemExit(f"{what} refused: {err}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = canon.canonical_bytes(record)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise AlreadyReserved(
            f"{what} refused: {subject} is already reserved "
            f"({os.path.relpath(path, q_out)}); {tail}")
    def fsync_best_effort():
        # the reservation is authoritative by existence, so whatever is on
        # disk must survive a crash that lands right after this function
        # exits, on every exit path; failures here are swallowed because
        # the refusal that follows must not depend on them
        try:
            os.fsync(fd)
        except OSError:
            pass
        try:
            dfd = os.open(os.path.dirname(path), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass

    try:
        try:
            canon.write_all(fd, data, "head reservation")
            os.fsync(fd)
            on_disk = os.fstat(fd).st_size
            if on_disk != len(data):
                raise canon.ShortWriteError(
                    f"head reservation: {on_disk} byte(s) on disk for a "
                    f"{len(data)} byte record after fsync")
        except BaseException as err:
            # The exclusive file exists and may hold partial bytes. No
            # session exists yet, so nothing reached the model; but the
            # reservation is authoritative by existence (spent_head_reasons
            # refuses on lexists before it parses anything), so the head is
            # treated as spent rather than un-reserved. Make that durable
            # first, for every exception class including an operator
            # interrupt; then refuse (OSError) or propagate (anything else).
            fsync_best_effort()
            if isinstance(err, OSError):
                raise SystemExit(
                    f"{what} refused: reservation for {subject} "
                    f"could not be durably written ({err}); {subject} stays "
                    f"reserved and spent; no session was constructed; {tail}")
            raise
    finally:
        os.close(fd)
    try:
        dfd = os.open(os.path.dirname(path), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError as err:
        raise SystemExit(
            f"{what} refused: reservation for {subject} was written "
            f"but its directory could not be fsynced ({err}); {subject} stays "
            f"reserved and spent; no session was constructed; {tail}")
    return path


def _write_record(q_out, record, prefix):
    data = canon.canonical_bytes(record)
    rec_sha = canon.bytes_digest(data)
    rec_path = os.path.join(q_out, f"{prefix}{rec_sha}.json")
    with open(rec_path, "xb") as f:
        f.write(data)
    return rec_sha, rec_path


def write_attempt_record(q_out, record):
    """Immutable, content-addressed attempt record. Separate seam so a
    write failure here can be injected by tests (18321030 finding 2)."""
    return _write_record(q_out, record, QUALIFY_RECORD_PREFIX)


def write_binding_record(a_out, record):
    """The binding path's immutable attempt record; its own seam. Written
    durably (temporary file, write_all, fsync, link into place, directory
    fsync) so an interrupt can never leave a partial file under the name of
    the complete record (pass three, finding 3); the qualify path keeps its
    own writer unchanged."""
    data = canon.canonical_bytes(record)
    rec_sha = canon.bytes_digest(data)
    rec_path = os.path.join(a_out, f"{BINDING_RECORD_PREFIX}{rec_sha}.json")
    fd, tmp = tempfile.mkstemp(prefix=".tmp-record-", suffix=".json", dir=a_out)
    try:
        canon.write_all(fd, data, "binding attempt record")
        os.fsync(fd)
        if os.fstat(fd).st_size != len(data):
            raise canon.ShortWriteError("binding attempt record: size on disk "
                                        "differs from the payload after fsync")
        os.fchmod(fd, 0o644)
        os.close(fd)
        fd = None
        os_link(tmp, rec_path)   # FileExistsError: the record already exists
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    dfd = os.open(a_out, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return rec_sha, rec_path


def append_ledger(q_out, entry, ledger_name=QUALIFY_LEDGER, artifact_version=
                  "foundry-pass-2-qualification-ledger/experimental-v0.1"):
    """Ledger projection of the attempt records. Separate seam so a write
    failure here can be injected by tests (18321030 finding 2). The ledger
    is a convenience view; refusal never depends on it alone."""
    ledger = os.path.join(q_out, ledger_name)
    # lstat-gated read, no-follow; then a same-directory temporary regular
    # file, fsync, atomic replace (18321488 finding 2: open(..., 'wb') on a
    # symlinked ledger overwrote its external target)
    canon.refuse_unless_regular(ledger, "ledger")
    entries = (canon.load_json_regular(ledger)["attempts"]
               if canon.is_regular(ledger) else [])
    entries.append(entry)
    canon.write_canonical_atomic(ledger, {
        "artifact_version": artifact_version,
        "attempts": entries})
    return ledger


def append_binding_ledger(a_out, entry):
    """The binding path's ledger projection; its own seam."""
    return append_ledger(a_out, entry, BINDING_LEDGER,
                         "foundry-pass-2-binding-ledger/experimental-v0.1")


def check_evidence_paths(q_out, root=None, allowed_dirs=(RESERVATIONS_DIR,)):
    """Path-boundary gate for the mutable evidence root, run BEFORE any
    reservation is written and before any pre-existing evidence is read
    (18321488 blocking finding 2; authorized by 18321531). The evidence
    directories are untracked, so a git-clean tree says nothing about
    what sits in them. With lstat, never following links:

    - q_out and every ancestor below the pass root must be real
      directories (or absent);
    - every entry directly inside q_out must be a regular file, except the
      directories named in `allowed_dirs` (the reservations directory by
      default; the review path adds claims, run-records, outputs, and
      command-records), each of which must be a real directory whose
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
        if name in allowed_dirs:
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


def git_head(what="qualification"):
    """Exact commit sha and clean-tree flag, or a hard stop. A git failure
    used to read as head '' with a clean tree (adversary F2: two model
    calls spent at no head, ledger line naming no head)."""
    rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True, cwd=PASS2)
    status = subprocess.run(["git", "status", "--porcelain",
                             "--untracked-files=no"], capture_output=True,
                            text=True, cwd=PASS2)
    if rev.returncode != 0 or status.returncode != 0:
        raise SystemExit(f"{what} refused: git could not report the "
                         f"head (rev-parse rc={rev.returncode} "
                         f"{rev.stderr.strip()[:200]!r}; status "
                         f"rc={status.returncode} {status.stderr.strip()[:200]!r})")
    head = rev.stdout.strip()
    if not valid_head(head):
        raise SystemExit(f"{what} refused: git reported "
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


def known_attempt_ids(q_out, record_prefix=QUALIFY_RECORD_PREFIX,
                      ledger_name=QUALIFY_LEDGER):
    """Every attempt_id already recorded under q_out (attempt records and
    ledger). Evidence produced by this run must carry a NEW id."""
    ids = set()
    if os.path.isdir(q_out):
        for name in os.listdir(q_out):
            if name.startswith(record_prefix) and name.endswith(".json"):
                try:
                    ids.add(canon.load_json_regular(
                        os.path.join(q_out, name)).get("attempt_id"))
                except Exception:  # noqa: BLE001
                    pass
    ledger = os.path.join(q_out, ledger_name)
    if canon.is_regular(ledger):
        try:
            for a in canon.load_json_regular(ledger)["attempts"]:
                ids.add(a.get("attempt_id"))
        except Exception:  # noqa: BLE001
            pass
    ids.discard(None)
    return ids


def reconcile_attempt(session, transcript_path, result, error, prior_ids, what):
    """The receipt for one spent attempt, reconciled against the live
    session object and the evidence on disk. Moved verbatim out of
    qualify() so the binding path publishes the same receipt through the
    same code (18371886); the accounting branches are pinned by the qualify
    suites and the prior-attempt-id refusal by the binding suite. Returns
    the persisted evidence and the published counts, or raises SystemExit
    exactly as qualify() did."""
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
            raise SystemExit(f"{what} attempt left no evidence on "
                             f"disk but the session reports {live} CLI "
                             "invocation(s) started; treat the head as "
                             f"spent (it stays reserved): {error}")
        # nothing was persisted and the session reports nothing started, so
        # no model call was made; the head has not spent its attempt
        raise SystemExit(f"{what} did not start an attempt: "
                         f"{error or 'no evidence written'}")
    persisted = canon.load_json_regular(transcript_path)
    if persisted.get("attempt_id") in prior_ids:
        raise SystemExit(f"{what} evidence carries a previously "
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
        raise SystemExit(f"{what} evidence disagrees with outcome: "
                         f"{persisted.get('preflight_result')!r} vs {result}")
    # the durable evidence is the content-addressed sibling, never the
    # working file (hole 1: the working file is rewritten by the next attempt)
    evidence_dir = os.path.dirname(transcript_path)
    sibling_manifest = canon.load_json_regular(os.path.join(
        evidence_dir, reviewer.PASSED_PREFLIGHT_MANIFEST if result == "PASS"
        else reviewer.FAILED_PREFLIGHT_MANIFEST))
    evidence_sha = _sha(transcript_path)
    sibling = [m for m in sibling_manifest["members"]
               if m["sha256"] == evidence_sha]
    if len(sibling) != 1 or not canon.is_regular(
            os.path.join(evidence_dir, sibling[0]["path"])):
        raise SystemExit(f"{what} evidence has no content-addressed "
                         f"sibling on disk for {evidence_sha}")
    return {"persisted": persisted, "calls": calls,
            "invocations": invocations, "accounting": accounting,
            "reconciliation": reconciliation, "evidence_sha": evidence_sha,
            "evidence_file": sibling[0]["path"]}


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
    receipt = reconcile_attempt(session, transcript_path, result, error,
                                prior_ids, "qualification")
    persisted = receipt["persisted"]
    calls = receipt["calls"]
    invocations = receipt["invocations"]
    accounting = receipt["accounting"]
    reconciliation = receipt["reconciliation"]
    evidence_sha = receipt["evidence_sha"]
    evidence_file = receipt["evidence_file"]
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
    probe transcript, identity, reservations, claims, each shard record,
    each installed output, each command record. A rebuildable INDEX,
    never the source of truth (18376129): rewritten durably (temporary
    file, fsync, atomic replace, symlink destination refused) after every
    terminal exit, and every member is inspected with lstat and read
    without following links."""
    A_OUT = a_out or globals()["A_OUT"]
    members = []
    def add(kind, rel):
        path = os.path.join(A_OUT, rel)
        if canon.is_regular(path):
            data = canon.read_regular_bytes(path)
            members.append({"kind": kind, "path": rel,
                            "sha256": canon.bytes_digest(data),
                            "byte_length": len(data)})
    add("leak-probe-transcript", "leak-probe-transcript.json")
    add("failed-preflight-manifest", reviewer.FAILED_PREFLIGHT_MANIFEST)
    add("passed-preflight-manifest", reviewer.PASSED_PREFLIGHT_MANIFEST)
    for name in sorted(os.listdir(A_OUT)):
        if "-FAILED-" in name and name.endswith(".json"):
            add("failed-preflight-evidence", name)
        elif "-PASSED-" in name and name.endswith(".json"):
            add("passed-preflight-evidence", name)
    add("identity", "reviewer-identity.json")
    # the kinds the gate consumes (engine/gate.py check_run_record_manifest
    # requires "run-record") keep their names; the review path's new kinds
    # are additive (isolated adversary on this head, finding 2). Temporary
    # files are never members (finding 12).
    for sub, kind in ((RESERVATIONS_DIR, "reservation"), (CLAIMS_DIR, "shard-claim"),
                      (RUN_RECORDS_DIR, "run-record"), (OUTPUTS_DIR, "fixed-output"),
                      (COMMAND_RECORDS_DIR, "command-record")):
        d = os.path.join(A_OUT, sub)
        if canon.is_real_dir(d):
            for name in sorted(os.listdir(d)):
                if name.startswith("."):
                    continue
                if sub == OUTPUTS_DIR and not (
                        name.endswith(".json") and SHARD_ID_RE.fullmatch(name[:-5])
                        and "-REFUSED-" not in name):
                    continue   # only <shard_id>.json is a fixed output
                if sub in (RUN_RECORDS_DIR, COMMAND_RECORDS_DIR) and \
                        RECORD_NAME_RE.fullmatch(name) is None:
                    continue   # only content-addressed records are members
                add(kind, os.path.join(sub, name))
    manifest = {"artifact_version": "foundry-pass-2-run-record-manifest/experimental-v0.2",
                "reviewer_role": "reviewer_a", "members": members}
    return canon.write_canonical_atomic(
        os.path.join(A_OUT, "run-record-manifest.json"), manifest)


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


def shard_states(out_root=None, a_out=None):
    """The state of every shard in the bound manifest, rebuilt from the
    immutable artifacts alone (claims, shard records, outputs), never from
    the manifest index or the ledger (18376129). Every relationship is
    recomputed: a record must hash to its name, name the shard and a claim
    that exists, and attest an output that is on disk with that digest and
    length. Read-only; nothing is opened through a link."""
    out_root = out_root or OUT
    a_out = a_out or A_OUT
    manifest = canon.load_json(os.path.join(out_root, "shard-manifest.json"))
    claims_dir = os.path.join(a_out, CLAIMS_DIR)
    records_dir = os.path.join(a_out, RUN_RECORDS_DIR)
    outputs_dir = os.path.join(a_out, OUTPUTS_DIR)
    identity_path = os.path.join(a_out, IDENTITY_FILE)
    identity_sha = None
    identity = None
    if canon.is_regular(identity_path):
        identity_bytes = canon.read_regular_bytes(identity_path)
        identity_sha = canon.bytes_digest(identity_bytes)
        try:
            identity = json.loads(identity_bytes.decode("utf-8"))
        except Exception:  # noqa: BLE001
            identity = None
    states = {}
    for m in manifest["shards"]:
        sid = m["shard_id"]
        claim = os.path.join(claims_dir, f"{sid}.json")
        claimed = os.path.lexists(claim)
        found = _existing_record(records_dir, f"{sid}.", {"shard_id": sid})
        output = os.path.join(outputs_dir, f"{sid}.json")
        problems = []
        state = "pending"
        rec = None
        if found is not None:
            rec_sha, rec_path = found
            data = canon.read_regular_bytes(rec_path)
            if canon.bytes_digest(data) != rec_sha:
                problems.append("record does not hash to its name")
            rec = json.loads(data.decode("utf-8"))
            others = [n for n in os.listdir(records_dir)
                      if n.startswith(f"{sid}.") and n.endswith(".json")
                      and n != os.path.basename(rec_path)]
            for n in others:
                try:
                    other = canon.load_json_regular(os.path.join(records_dir, n))
                except Exception:  # noqa: BLE001
                    other = {}
                if other.get("shard_id") == sid:
                    problems.append("more than one record for this shard")
                    break
            if not claimed:
                problems.append("record without a claim")
            else:
                try:
                    claim_meta = canon.load_json_regular(claim)
                except Exception as err:  # noqa: BLE001
                    claim_meta = None
                    if not (rec.get("result") == "FAIL" and rec.get("phase") == "claim"):
                        # a claim whose bytes never landed is what a record
                        # in phase claim attests; anywhere else it is damage
                        problems.append(f"claim unreadable ({type(err).__name__})")
                if claim_meta is not None and (
                        claim_meta.get("shard_id") != sid
                        or claim_meta.get("command_attempt_id")
                        != rec.get("command_attempt_id")):
                    problems.append("claim and record disagree on the shard "
                                    "or the command")
            if rec.get("input_sha256") != m["sha256"]:
                problems.append("record input digest differs from the manifest")
            if rec.get("input_path") != m["path"]:
                problems.append("record input path differs from the manifest")
            if identity_sha is not None and rec.get("identity_sha256") != identity_sha:
                problems.append("record identity digest differs from the "
                                "identity on disk")
            try:
                problems.extend(_record_relationship_problems(
                    a_out, rec, rec_sha, claim, sid, identity, identity_sha))
            except Exception as err:  # noqa: BLE001 - malformed is CORRUPT, not a crash
                problems.append(f"record malformed ({type(err).__name__}: "
                                f"{str(err)[:120]})")
            if rec.get("result") == "DONE":
                if not canon.is_regular(output):
                    problems.append("attested output missing")
                else:
                    out_bytes = canon.read_regular_bytes(output)
                    if (canon.bytes_digest(out_bytes) != rec.get("output_sha256")
                            or len(out_bytes) != rec.get("output_byte_length")):
                        problems.append("output on disk does not match the "
                                        "record's attestation")
            elif canon.is_regular(output):
                problems.append("output present for a shard whose record is "
                                f"{rec.get('result')}")
            state = rec.get("result") or "FAIL"
        elif claimed:
            # a claim with no record: spent and unattested, whether or not an
            # output landed; never re-run, never trusted, reported as such
            state = "UNATTESTED"
        elif canon.is_regular(output):
            state = "UNATTESTED"
            problems.append("output present without a claim or a record")
        if problems:
            state = "CORRUPT"
        states[sid] = {"state": state, "record_count": m["record_count"],
                       "problems": problems,
                       "phase": rec.get("phase") if rec else None,
                       "error": rec.get("error") if rec else None,
                       "output_sha256": rec.get("output_sha256") if rec else None}
    return states


RESERVATION_RECORD_FIELDS = (
    "ruling_id", "head", "model_id", "ruled_model_id", "model_version_or_build",
    "configuration_sha256", "auxiliary_model_policy", "attempts_allowed",
    "command_attempt_id", "identity_sha256")
RESERVATION_IDENTITY_FIELDS = (
    ("head", "head"), ("model_id", "model_id"),
    ("model_version_or_build", "model_version_or_build"),
    ("configuration_sha256", "configuration_sha256"),
    ("environment_boundary_sha256", "environment_boundary_sha256"),
    ("auxiliary_model_policy", "auxiliary_model_policy"),
    ("bindings", "bindings"))


def _reservation_problems(a_out, res, res_sha, identity, identity_sha, label):
    """The reservation is the authority artifact for a command: it is held
    against the identity on disk on every field it binds, and whoever
    names it (a claim, a record, a terminal record) is held against its
    bytes (second isolated pass, findings 2 and 3: the reservation was
    written as the authority and never used as one)."""
    problems = []
    if res.get("purpose") != "governed-review":
        problems.append(f"{label}: reservation is not a governed-review reservation")
    if identity is not None:
        for res_field, id_field in RESERVATION_IDENTITY_FIELDS:
            if res.get(res_field) != identity.get(id_field):
                problems.append(f"{label}: reservation {res_field} differs from "
                                "the identity on disk")
    if identity_sha is not None and res.get("identity_sha256") != identity_sha:
        problems.append(f"{label}: reservation identity digest differs from "
                        "the identity on disk")
    if res.get("call_ceiling") != len(res.get("shards", [])) or \
            res.get("attempts_allowed") != REVIEW_ATTEMPTS:
        problems.append(f"{label}: reservation ceiling or attempts are not "
                        "the ones this harness reserves")
    return problems


def _record_relationship_problems(a_out, rec, rec_sha, claim, sid, identity=None,
                                  identity_sha=None):
    """Every relationship a shard record asserts, recomputed from the
    artifacts it names (isolated adversary on this head, finding 6: only
    three were recomputed, and a record rewritten with a fabricated ruling,
    command, identity, response, and count passed as DONE; second pass,
    findings 2 and 3: the reservation was never recomputed, and the record's
    copies of the binding fields never held against it)."""
    problems = []
    raw = rec.get("raw_response")
    if raw is not None and canon.content_digest(raw) != rec.get("raw_response_sha256"):
        problems.append("raw response does not hash to the record's digest")
    reservation = os.path.join(a_out, RESERVATIONS_DIR,
                               f"{REVIEW_RESERVATION_PREFIX}{rec.get('ruling_id')}.json")
    if rec.get("reservation_path") != os.path.relpath(reservation, a_out):
        problems.append("record names a reservation path that is not its ruling's")
    res = None
    res_sha = None
    if not canon.is_regular(reservation):
        problems.append("the reservation the record names is absent")
    else:
        res_bytes = canon.read_regular_bytes(reservation)
        res_sha = canon.bytes_digest(res_bytes)
        try:
            res = json.loads(res_bytes.decode("utf-8"))
        except Exception as err:  # noqa: BLE001
            res = None
            problems.append(f"reservation unreadable ({type(err).__name__})")
        if res is not None:
            for field in RESERVATION_RECORD_FIELDS:
                if res.get(field) != rec.get(field):
                    problems.append(f"reservation and record disagree on {field}")
            named = {s.get("shard_id"): s.get("input_sha256")
                     for s in res.get("shards", []) if isinstance(s, dict)}
            if sid not in named:
                problems.append("the reservation does not name this shard")
            elif named[sid] != rec.get("input_sha256"):
                problems.append("reservation and record disagree on the input digest")
            problems.extend(_reservation_problems(a_out, res, res_sha, identity,
                                                  identity_sha, "record"))
    if identity is not None:
        for field in ("head", "model_id", "ruled_model_id", "model_version_or_build",
                      "configuration_sha256", "auxiliary_model_policy"):
            if rec.get(field) != identity.get(field if field != "ruled_model_id"
                                              else "model_id"):
                problems.append(f"record {field} differs from the identity on disk")
    if rec.get("claim_sha256") is not None and canon.is_regular(claim):
        claim_bytes = canon.read_regular_bytes(claim)
        if canon.bytes_digest(claim_bytes) != rec.get("claim_sha256"):
            problems.append("claim bytes do not hash to the record's claim digest")
        try:
            claim_meta = json.loads(claim_bytes.decode("utf-8"))
        except Exception:  # noqa: BLE001
            claim_meta = {}
        if res_sha is not None and claim_meta.get("reservation_sha256") != res_sha:
            problems.append("the claim's reservation digest is not the "
                            "reservation on disk")
        for field in ("ruling_id", "head", "model_id", "identity_sha256",
                      "input_sha256", "reservation_path"):
            if claim_meta.get(field) != rec.get(field):
                problems.append(f"claim and record disagree on {field}")
    command = _existing_record(os.path.join(a_out, COMMAND_RECORDS_DIR),
                               f"{rec.get('command_attempt_id')}.",
                               {"command_attempt_id": rec.get("command_attempt_id")})
    if command is None:
        problems.append("no terminal command record for this shard's command")
    else:
        cmd_sha, cmd_path = command
        data = canon.read_regular_bytes(cmd_path)
        if canon.bytes_digest(data) != cmd_sha:
            problems.append("terminal command record does not hash to its name")
        cmd = json.loads(data.decode("utf-8"))
        listed = {s.get("shard_id"): s for s in cmd.get("shards", [])
                  if isinstance(s, dict)}
        if sid not in listed:
            problems.append("the terminal command record does not list this shard")
        elif listed[sid].get("record_sha256") != rec_sha or \
                listed[sid].get("result") != rec.get("result"):
            problems.append("the terminal command record disagrees with the "
                            "shard record")
        for field in ("ruling_id", "head", "model_id", "identity_sha256",
                      "model_version_or_build", "configuration_sha256",
                      "auxiliary_model_policy"):
            if cmd.get(field) != rec.get(field):
                problems.append(f"the terminal command record and the shard "
                                f"record disagree on {field}")
        if res_sha is not None and cmd.get("reservation_sha256") != res_sha:
            problems.append("the terminal command record's reservation digest "
                            "is not the reservation on disk")
    if rec.get("result") == "DONE":
        usage = rec.get("observed_model_usage") or []
        # the policy and the model the usage is judged against are the
        # identity's, never the record's own copies (second pass, finding 3:
        # a forged triple always agreed with itself)
        model = identity.get("model_id") if identity else rec.get("model_id")
        policy = (identity.get("auxiliary_model_policy") if identity
                  else rec.get("auxiliary_model_policy")) or {}
        if (rec.get("cli_invocations") != REVIEW_ATTEMPTS
                or rec.get("model_calls") != 1
                or rec.get("verdict") != "fixed"
                or rec.get("attempts_allowed") != REVIEW_ATTEMPTS
                or not usage or not isinstance(usage[0], dict)
                or not usage[0].get("model_usage_reported")
                or aux_policy_violations(usage, model, policy)
                or rec.get("auxiliary_model_violations")):
            problems.append("a DONE record whose accounting, verdict, or model "
                            "usage does not satisfy the ruling's sentence")
    return problems


def command_states(a_out=None):
    """Every review reservation under a_out with the terminal command
    record it should have, rebuilt from the artifacts: a reservation with
    no command record is an unfinalized command (finding 3); a command
    record must hash to its name, name its reservation's command, and list
    exactly the reservation's shards."""
    a_out = a_out or A_OUT
    res_dir = os.path.join(a_out, RESERVATIONS_DIR)
    out = []
    if not canon.is_real_dir(res_dir):
        return out
    identity_path = os.path.join(a_out, IDENTITY_FILE)
    identity_sha = None
    identity = None
    if canon.is_regular(identity_path):
        identity_bytes = canon.read_regular_bytes(identity_path)
        identity_sha = canon.bytes_digest(identity_bytes)
        try:
            identity = json.loads(identity_bytes.decode("utf-8"))
        except Exception:  # noqa: BLE001
            identity = None
    for name in sorted(os.listdir(res_dir)):
        if not (name.startswith(REVIEW_RESERVATION_PREFIX) and name.endswith(".json")):
            continue
        ruling = name[len(REVIEW_RESERVATION_PREFIX):-5]
        problems = []
        res_sha = None
        try:
            res_bytes = canon.read_regular_bytes(os.path.join(res_dir, name))
            res_sha = canon.bytes_digest(res_bytes)
            res = json.loads(res_bytes.decode("utf-8"))
        except Exception as err:  # noqa: BLE001
            res = {}
            # a reservation whose bytes never landed is what a terminal
            # record in phase reservation attests (finding 3a); anywhere
            # else it is damage
            explained = _existing_record(os.path.join(a_out, COMMAND_RECORDS_DIR),
                                         "", {"ruling_id": ruling,
                                              "phase": "reservation",
                                              "result": "FAIL"})
            if explained is None:
                problems.append(f"reservation unreadable ({type(err).__name__})")
            else:
                res = {"command_attempt_id": canon.load_json_regular(
                    explained[1]).get("command_attempt_id")}
        cid = res.get("command_attempt_id")
        found = (_existing_record(os.path.join(a_out, COMMAND_RECORDS_DIR),
                                  f"{cid}.", {"command_attempt_id": cid})
                 if cid else None)
        result = None
        if found is None:
            problems.append("no terminal command record (unfinalized)")
        else:
            cmd_sha, cmd_path = found
            data = canon.read_regular_bytes(cmd_path)
            if canon.bytes_digest(data) != cmd_sha:
                problems.append("terminal command record does not hash to its name")
            cmd = json.loads(data.decode("utf-8"))
            result = cmd.get("result")
            if cmd.get("ruling_id") != ruling:
                problems.append("command record names another ruling")
            want = [s.get("shard_id") for s in res.get("shards", []) if isinstance(s, dict)]
            got = [s.get("shard_id") for s in cmd.get("shards", []) if isinstance(s, dict)]
            if "shards" in res and want != got:
                problems.append("command record does not list the reservation's shards")
            if "shards" in res:
                # a readable reservation is held against the identity and
                # the terminal record on every field it binds (second
                # isolated pass, findings 2 and 3)
                try:
                    for field in ("head", "identity_sha256", "model_id",
                                  "ruled_model_id", "model_version_or_build",
                                  "configuration_sha256", "auxiliary_model_policy",
                                  "call_ceiling", "attempts_allowed",
                                  "command_attempt_id"):
                        if cmd.get(field) != res.get(field):
                            problems.append(f"command record and reservation "
                                            f"disagree on {field}")
                    if cmd.get("reservation_sha256") != res_sha:
                        problems.append("command record's reservation digest is "
                                        "not the reservation on disk")
                    problems.extend(_reservation_problems(
                        a_out, res, res_sha, identity, identity_sha, "command"))
                except Exception as err:  # noqa: BLE001
                    problems.append(f"malformed ({type(err).__name__})")
        out.append({"ruling_id": ruling, "command_attempt_id": cid,
                    "result": result, "problems": problems})
    return out


def status(out_root=None, a_out=None):
    for c in command_states(a_out):
        line = f"command ruling {c['ruling_id']} {c['command_attempt_id']} {c['result'] or 'UNFINALIZED'}"
        if c["problems"]:
            line += " PROBLEMS: " + "; ".join(c["problems"])
        print(line)
    for sid, s in shard_states(out_root, a_out).items():
        line = f"{sid} {s['record_count']} {s['state']}"
        if s["output_sha256"]:
            line += f" output {s['output_sha256']}"
        if s["error"]:
            line += f" ({s['phase']}: {s['error']})"
        if s["problems"]:
            line += " PROBLEMS: " + "; ".join(s["problems"])
        print(line)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "identity":
        bind_identity()
    elif mode == "qualify":
        qualify()
    elif mode == "review":
        review(sys.argv[2:])
    else:
        status()
