# Invocation A — route-only final sync

- 영향받는 Root Cartography 좌표: `Capability 상태 / attachment export`, `As-built routes / CLI export`
- merge candidate diff: `src/cli/export.ts`가 이제 `src/export/ExportService.ts`로 dispatch한다. module owner, storage policy, public boundary, global decision은 바뀌지 않았다.
- implementation Cartography impact: attachment export `planned → landed`, 새 CLI export → ExportService edge, 관련 epic-21과 decision 0021.
- 상태 증거: `tests/integration/export.test.ts` PASS, `message-hub export attachment-1 --out /tmp/export` exit 0, 결과는 byte-for-byte 일치.
- 문서 정책: `docs/architecture.md`는 canonical local-only/ignored private documentation이며 code PR에 추가하면 안 된다.
- 변경 금지 sentinel: message search, scheduler cleanup, Global decisions는 byte-for-byte 그대로 보존해야 한다.
