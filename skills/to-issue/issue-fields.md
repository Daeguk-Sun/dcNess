# /to-issue Field SSOT

This file is the single source of truth for `/to-issue` issue classification fields. `SKILL.md` must reference this file instead of duplicating these option lists. The broader Project lifecycle SSOT is [`../../docs/plugin/github-project.md`].

When GitHub Project field options or repo labels diverge from this file, stop before creating the issue and report the setup gap. Do not guess option ids or create labels implicitly. repo label 6종은 IssueType 축과 같은 의미로 쓴다.

## Status

| Value | Meaning |
| --- | --- |
| `Todo` | Issue has been registered but no target workflow has started yet. |
| `In progress` | A target workflow such as `/spec`, `/design`, `/impl`, or `/ux` has started for the issue. |
| `Done` | The issue was completed by a merged PR that actually closes/fixes/resolves it. |

## IssueType

| Value | Repo label | Meaning |
| --- | --- | --- |
| `epic` | `epic` | Large outcome that groups multiple features or stories. |
| `feature` | `feature` | User-facing or operator-facing capability. |
| `story` | `story` | End-to-end vertical slice that can be implemented and verified independently. |
| `task` | `task` | Non-user-facing work item with a concrete completion condition. |
| `subTask` | `subTask` | Child work item that only makes sense under a parent issue. |
| `bug` | `bug` | Broken or regressed behavior that should be restored. |

## Priority

| Value | Meaning |
| --- | --- |
| `blocker` | Prevents dependent work or release from moving forward. |
| `critical` | High-risk or time-sensitive issue that should be handled before normal major work. |
| `major` | Normal important work with meaningful product, workflow, or maintenance value. |
| `minor` | Useful but lower urgency work. |
| `trivial` | Small cleanup or polish with limited impact. |

## Usage Rules

- Use the selected `IssueType` value as the repo label.
- Set Project `IssueType` and Project `Priority` to the exact values above.
- Set Project `Status` to `Todo` when registering the issue.
- Move Project `Status` to `In progress` when a target workflow starts.
- Move Project `Status` to `Done` only from `Closes`, `Fixes`, `Resolves`, or GitHub closing references after default-branch merge. `Part of #N` is not a Done signal.
- If a parent issue exists, reference it only. `/to-issue` does not close or rewrite the parent.
