# 30-Second Demo

dcNess is easiest to understand as a PR workflow guard: it blocks a skipped gate,
shows the recovery path, and lets the normal PR flow continue after validation.

## Hook Block To Recovery

```text
Claude tries to call pr-reviewer before code-validator PASS
→ dcNess blocks the call

[dcness] BLOCK
reason: pr-reviewer cannot run before validation PASS
next: run code-validator read-only, then retry pr-reviewer

Run code-validator
→ code-validator returns PASS

Retry pr-reviewer
→ pr-reviewer runs read-only
→ review passes

Run tests
→ tests pass

Create PR
→ branch → PR → merge gate
```

The useful part is not the number of steps. The useful part is that a skipped
review cannot silently become a PR. The hook stops the unsafe action, names the
missing gate, and points back to the shortest valid recovery path.

## What This Shows

- Work order is enforced before PR creation.
- Review agents stay read-only.
- Recovery is local and explicit.
- The user-facing command surface stays small; `/impl` remains the default entrypoint.
