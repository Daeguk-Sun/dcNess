## Issue Brief

**IssueType:** {{IssueType}}
**Priority:** {{Priority}}
**Summary:**
{{한 줄로 이 이슈가 달성해야 하는 결과를 쓴다.}}

**Current behavior / Context:**
{{지금 어떤 일이 벌어지는지 또는 어떤 배경 위에서 이 작업이 필요한지 쓴다.}}
{{버그라면 깨진 동작과 관측 조건을 쓴다.}}
{{기능/작업이라면 현재 없는 능력이나 현재 운영상의 gap 을 쓴다.}}

**Desired behavior / What to build:**
{{작업 완료 후 시스템, 사용자 경험, 문서, 하네스가 어떤 상태여야 하는지 쓴다.}}
{{end-to-end behavior 를 설명하고 layer-by-layer 구현 계획을 쓰지 않는다.}}
{{구현 파일 경로, line number, 코드 조각, 특정 함수 수정 지시는 기본적으로 쓰지 않는다.}}
{{예외적으로 prototype 의 state machine, schema, type shape 가 prose 보다 결정을 정확히 담는 경우만 짧게 포함하고 prototype 출처를 명시한다.}}

**Key interfaces / Contracts:**
- {{사용자가 보게 되는 command, API, 문서 공개 노출 범위, config shape, type/field 이름 같은 안정적인 계약을 쓴다.}}
- {{현재 파일 위치가 아니라 바뀌어야 하는 인터페이스나 행동 계약을 쓴다.}}
- {{UI 성격 이슈면 `UI 기준:` 으로 기준 canvas / 목업 / flow 문서, 사용자 제공 이미지·스케치 링크, 또는 `목업 없이(시각 구조 불변 사유=<reason>)` 를 쓴다. non-UI 면 생략한다.}}
- {{모르면 추측하지 말고 비워두거나 명확화 질문으로 남긴다.}}

**Acceptance criteria:**
- [ ] [command] {{독립적으로 검증 가능한 command/eval/test 와 관측할 통과 조건을 포함한 완료 조건}}
- [ ] [agent-read] {{agent 가 산출물·diff·계약을 읽어 독립적으로 검증할 구체적인 완료 조건}}

**Human verification / 사람 확인 안내:**
- {{사람의 시각·취향·운영 승인 등이 필요하면 체크박스 없이 적는다. 없으면 `없음`}}

**Blocked by:**
None - can start immediately
{{또는 blocking issue 링크 목록.}}

**Out of scope:**
- {{이 이슈에서 하지 않을 것}}
- {{관련 있어 보이지만 별도 이슈로 둘 것}}
