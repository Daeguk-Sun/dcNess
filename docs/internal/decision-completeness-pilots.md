# 결정 완전성 pilot 기록

이 기록은 현재 저장소의 실제 작업 두 건을 결정 완전성 계약으로 다시 읽은 결과다. 질문 수를 늘리는 것이 아니라, 구현 방향을 바꾸는 선택이 기존 근거로 닫히는지와 남은 사람 판단을 분리하는 데 목적이 있다.

## Pilot A — 제품 결과 evidence loop

원본 위치: 이 저장소의 작업 이슈 #1064
원본 갱신 시각: `2026-07-11T09:50:42Z`
원본 본문 SHA-256: `65d3bc47b7af4251e5f8c36d85399fa6ebd5eaa999eb28eaf3a973f99655407c` (UTF-8 본문 끝 LF 포함)

원본 기준은 issue 본문의 `Summary`, `Desired behavior / What to build`, `개인 개발자 비용 가드`, `Acceptance criteria`, `Human verification / 사람 확인 안내`다. 아래 각 행은 그 위치까지 지정해 원본이 갱신되면 다시 대조할 수 있게 한다.

| 중요한 선택 | 근거 상태 | 근거와 처리 결과 | 명세 또는 수용 기준 연결 |
|---|---|---|---|
| 과정 지표와 실제 제품 outcome을 분리한다 | 프로젝트 근거 | `Current behavior / Context`와 P0 2항: 기존 측정은 guard·review·merge를 설명하지만 실제 journey 성공을 증명하지 못한다 | `Acceptance criteria` 1항의 scorecard와 P3 2항의 공개 evidence에서 별도 denominator를 요구한다 |
| 추가 언어모델 trial은 월 최대 4회다 | 사용자 확정 | `Desired behavior` 서두와 `개인 개발자 비용 가드`: 개인 개발자 비용 상한으로 승인된 경계다 | P2와 `Acceptance criteria` 6항의 ablation 기록으로 연결한다 |
| 첫 실행 검증은 non-UI 1건과 UI 또는 실제 사용자 흐름 1건으로 제한한다 | 목표에서 도출 | P1 project-local pilot 3항과 `Out of scope`: 제품 경계를 두 형태로 확인하면서 범용 플랫폼 구축을 피하는 최소 pilot이다 | `Acceptance criteria` 3항의 두 journey command evidence와 사람 확인 안내로 연결한다 |
| 첫 ablation 후보의 구체 항목은 반복 비용이 확인된 선택형 구성요소 안에서 고른다 | 명시적 위임 | P2 1·5항이 후보의 선택 범위를 telemetry상 반복 비용과 선택형 구성요소로 제한하고, 그 안의 구체 후보 선택을 실행자에게 맡긴다 | `Acceptance criteria` 6항에서 실제 선택 근거와 keep/remove/hold 결정을 검증한다 |
| UI evidence가 사용자 관점에서 충분한가 | 미결정 처리 | `Human verification / 사람 확인 안내`: 자동 판정으로 대신하지 않고 실제 evidence가 생긴 뒤 소유자가 판단한다 | 해당 story의 사람 확인 안내에 남겨 agent가 승인하지 못하게 한다 |

질문 관찰: 승인된 목표와 기존 저장소 근거로 중요한 선택 네 건을 닫아 추가 질문은 만들지 않았다. UI evidence의 충분성만 실제 산출 이후 사람 판단으로 남겼다.

상태: **human verification 대기** — 질문이 불필요하게 많지 않으면서 구현 방향을 바꿀 선택이 충분히 드러났는지 사용자가 확인해야 한다.

## Pilot B — Epic 경계 Codebase Sanity

원본 위치: 이 저장소의 작업 이슈 #1062
원본 갱신 시각: `2026-07-11T08:26:13Z`
원본 본문 SHA-256: `50fbd886edbcdcc725a469c1faeda6117227b22c66c651b5999add09fac4eb78` (UTF-8 본문 끝 LF 포함)

원본 기준은 issue 본문의 `Summary`, `Desired behavior / What to build`, `Key interfaces / Contracts`, `Acceptance criteria`다. 아래 각 행은 그 위치까지 지정해 원본이 갱신되면 다시 대조할 수 있게 한다.

| 중요한 선택 | 근거 상태 | 근거와 처리 결과 | 명세 또는 수용 기준 연결 |
|---|---|---|---|
| 새 검수자를 만들지 않고 기존 read-only 구현 검수자의 내부 책임을 재사용한다 | 프로젝트 근거 | `Current behavior / Context`와 `Epic 단위 Sanity cadence`: 기존 검수자가 구현자와 분리돼 있고 quality·중복·테스트 신뢰도 판단을 이미 소유한다 | `Key interfaces / Contracts` 2항과 `Acceptance criteria` 1·11항에서 신규 공개 surface 없이 repo/affected-cone 의미 감사를 요구한다 |
| test·lint·build·coverage 명령 실행은 메인 workflow가 소유한다 | 프로젝트 근거 | `Epic 단위 Sanity cadence` 2항과 `Key interfaces / Contracts` 4항: read-only 검수자에게 실행·write 권한을 추가하지 않는다 | 실행 증거를 입력으로 받고 검수자는 의미 판정만 한다 |
| coverage 도구나 report가 없으면 UNKNOWN이다 | 목표에서 도출 | `Sanity evidence와 분류`와 `Key interfaces / Contracts` 6항: test count를 coverage로 추정하면 false-clean이 된다 | receipt와 `Acceptance criteria` 7·9항에 측정 불가를 그대로 보존한다 |
| 작은 저장소는 전체, 큰 저장소는 affected dependency cone을 기본 범위로 삼는다 | 명시적 위임 | `Epic 단위 Sanity cadence` 5항이 저장소 규모에 따른 탐색 범위를 구현자에게 맡기되 실제 scope 보고를 요구한다 | `Acceptance criteria` 2·9항에서 receipt에 code revision과 실제 감사 scope를 남긴다 |
| framework reachability와 intentional seam을 구분할 근거가 없는 후보 | 미결정 처리 | `Sanity evidence와 분류`: 삭제로 추정하지 않고 unknown/escalate로 남겨 rework 또는 소유자 결정을 요구한다 | dead-code 분류와 `Acceptance criteria` 6·9항의 남은 finding에 연결한다 |

질문 관찰: 기존 역할·권한·측정 정확도 근거로 네 건을 닫았고, 실제 reachability 근거가 없는 후보만 상황 발생 시 질문 또는 escalate 대상으로 남겼다.

상태: **human verification 대기** — 질문 과잉 없이 새 검수자 추가 여부, coverage 해석, 삭제 위험처럼 구현 방향을 바꾸는 선택이 드러났는지 사용자가 확인해야 한다.
