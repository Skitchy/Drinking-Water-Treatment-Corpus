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
import subprocess
import sys
import tempfile

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


def make_session(system_prompt, cwd):
    return reviewer.IsolatedSession(MODEL, system_prompt, cwd)


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


def git_head():
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, cwd=PASS2).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain",
                            "--untracked-files=no"], capture_output=True,
                           text=True, cwd=PASS2).stdout.strip()
    return head, dirty == ""


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
    if not clean:
        raise SystemExit("qualification refused: working tree is not clean "
                         f"at {head}")
    os.makedirs(Q_OUT, exist_ok=True)
    refuse_if_ledgered(os.path.join(Q_OUT, "qualification-ledger.json"), head)
    system_prompt = _read(os.path.join(ARI, "reviewer-system-prompt-v0.1.md"))
    template = load_template(FIXTURE_OUT)
    digests = bundle_digests(FIXTURE_OUT)
    schema = load_schema(FIXTURE_OUT)
    cwd = tempfile.mkdtemp(prefix="foundry-qualify-a-")
    session = make_session(system_prompt, cwd)
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
    if not os.path.isfile(transcript_path):
        # nothing was persisted, so no probe stage began and no model call
        # was made; the head has not spent its attempt
        raise SystemExit("qualification did not start an attempt: "
                         f"{error or 'no evidence written'}")
    persisted = canon.load_json(transcript_path)
    calls = sum(1 for t in persisted["transcripts"] if t["result"] is not None)
    invocations = sum(t.get("cli_invocations", 1 if t["result"] is not None
                            else 0) for t in persisted["transcripts"])
    if persisted.get("preflight_result") == "IN-PROGRESS" and result == "FAIL":
        # the harness never finalized (interrupted mid-attempt): ledger the
        # spent attempt as FAIL rather than exit without a line
        persisted["preflight_result"] = "FAIL"
        persisted["failure_reason"] = persisted.get("failure_reason") or error
        canon.write_canonical(transcript_path, persisted)
        reviewer.persist_failure(transcript_path, persisted)
    if persisted.get("preflight_result") != result:
        raise SystemExit("qualification evidence disagrees with outcome: "
                         f"{persisted.get('preflight_result')!r} vs {result}")
    # the durable evidence is the content-addressed sibling, never the
    # working file (hole 1: the working file is rewritten by the next attempt)
    sibling_manifest = canon.load_json(os.path.join(
        Q_OUT, reviewer.PASSED_PREFLIGHT_MANIFEST if result == "PASS"
        else reviewer.FAILED_PREFLIGHT_MANIFEST))
    evidence_sha = _sha(transcript_path)
    sibling = [m for m in sibling_manifest["members"]
               if m["sha256"] == evidence_sha]
    if len(sibling) != 1 or not os.path.isfile(os.path.join(Q_OUT, sibling[0]["path"])):
        raise SystemExit("qualification evidence has no content-addressed "
                         f"sibling on disk for {evidence_sha}")
    evidence_file = sibling[0]["path"]
    record = {
        "artifact_version": "foundry-pass-2-qualification-attempt/experimental-v0.1",
        "qualification_only": True,
        "eligible_for_binding": False,
        "reviewer_role": "reviewer_a",
        "model_id": MODEL,
        "model_version_or_build": cli_version(),
        "head": head,
        "attempt_id": persisted["attempt_id"],
        "started_utc": persisted["started_utc"],
        "result": result,
        "error": error,
        "model_calls": calls,
        "cli_invocations": invocations,
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
    data = canon.canonical_bytes(record)
    rec_sha = canon.bytes_digest(data)
    rec_path = os.path.join(Q_OUT, f"qualification-attempt-{rec_sha}.json")
    with open(rec_path, "xb") as f:
        f.write(data)
    ledger = os.path.join(Q_OUT, "qualification-ledger.json")
    entries = canon.load_json(ledger)["attempts"] if os.path.isfile(ledger) else []
    entries.append({"attempt_id": record["attempt_id"], "head": head,
                    "model": MODEL, "result": result, "model_calls": calls,
                    "cli_invocations": invocations,
                    "evidence_path": evidence_file,
                    "evidence_sha256": evidence_sha, "record_sha256": rec_sha,
                    "started_utc": record["started_utc"]})
    canon.write_canonical(ledger, {
        "artifact_version": "foundry-pass-2-qualification-ledger/experimental-v0.1",
        "attempts": entries})
    print("QUALIFICATION LEDGER LINE:")
    print(f"head {head} | model {MODEL} | attempt {record['attempt_id']} | "
          f"calls {calls} | invocations {invocations} | result {result} | "
          f"evidence {evidence_sha} ({evidence_file}) | record {rec_sha}")
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
