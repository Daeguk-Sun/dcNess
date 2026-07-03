You are validating dcNess headless worker/validator prose quality.

Use `{{REPO_ROOT}}` only if you need repository guidance; the case fixtures are
in `{{CASE_DIR}}`.

Read the files in `{{CASE_DIR}}`:

- `worker-good.md`
- `worker-bad.md`
- `validator-bad.md`

Assess whether each prose report gives the main orchestrator enough information
to make the next branch decision. Do not require JSON, a fixed table, markers,
or any rigid schema. Free prose is allowed.

Report concrete issues with file names and specific missing facts. Also mention
whether raw headless session logs should be preserved as files instead of being
dumped into the main context.

End your report with one conclusion enum word: PASS, FAIL, or ESCALATE.
