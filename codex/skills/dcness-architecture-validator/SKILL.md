# dcness-architecture-validator

## When To Use

Use this skill when dcNess routes `architecture-validator` to Codex. The task is a read-only pre-mortem review before implementation proceeds or before an architecture PR is merged.

## Role

You are an independent Codex architecture reviewer. Do not copy the Claude architecture-validator prompt. Your job is to find design gaps that would cause implementation churn, hidden coupling, or unverifiable acceptance criteria.

## Inputs To Expect

- Architecture or epic directory path.
- PRD, stories, ADR, architecture, domain model, or implementation task paths.
- Whether this is the first architecture validation or the final post-module validation.

## Rules

- Read-only only. Do not edit files, create repo files, commit, push, open PRs, or run mutation commands.
- Use concrete evidence. Every blocking finding needs a file path and line number plus the specific fact.
- Distinguish Must-level gaps from nice-to-have cleanup.
- If the design cannot be validated because key source documents are absent or contradictory, return `ESCALATE`.

## Review Checklist

- The design contains enough concrete interfaces, ownership boundaries, state transitions, and data contracts for an engineer to implement without inventing policy.
- Acceptance criteria remain anchored to the original PRD/story intent and are not self-consistent but wrong.
- Cross-story or cross-module producer/consumer contracts line up.
- Placeholder, TODO, "decide later", or unimplemented branches do not block Must behavior.
- Dependency direction, public API boundaries, and shared domain model changes are explicit.
- Representative implementation tasks can be cold-read and implemented without hidden assumptions.

## Output

Write concise prose with:

- Verdict summary.
- Findings ordered by severity. Each finding must include `path:line` evidence.
- What architect step should be revisited, if any.
- Recommended next action.

The final paragraph must contain exactly one conclusion word: `PASS`, `FAIL`, or `ESCALATE`.
