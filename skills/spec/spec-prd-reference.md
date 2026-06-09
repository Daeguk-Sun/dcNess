# Spec PRD Reference

`/spec` 내부 구현 절차가 PRD 초안을 만들 때 쓰는 참고 자료다. 진행 순서와 분기는 [`SKILL.md`](SKILL.md) 와 [`spec-routing.md`](spec-routing.md) 가 진본이다.

## 그릴미 패턴

메인은 `/grill-me` 원문 지시를 번역 없이 그대로 적용한다.

> Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.
>
> Ask the questions one at a time.
>
> If a question can be answered by exploring the codebase, explore the codebase instead.

추가 맥락:

- **이해 도달이 1차, PRD 작성은 그 기록** — 목표는 `shared understanding` 도달이고, PRD 산출물 체크리스트는 대화의 부산물이다.
- **체크리스트 충족 != 종료** — 핵심 분기에서 사용자가 납득하지 못했으면 빈칸이 다 차도 계속 질문한다.
- **객관식 후보보다 자연어 대화** — 메인은 2~3개 선택지를 던져 고르게 하는 방식에 갇히지 않는다. 사용자의 표현을 되묻고, 앞선 답변과 코드 탐색 결과를 연결하며, 맥락을 누적해 다음 질문을 만든다. 권장안은 제시하되 대화 흐름 안에서 합의한다.
- **why 부터, how 로 직행 금지** — 목적, 실제 페인, 규모를 먼저 판다.

## PRD 산출물 의무

`docs/prd.md` 는 [`templates/prd.md`](templates/prd.md)를 문서 템플릿으로 작성한다. 템플릿의 8개 섹션이 PRD 산출물 의무다. 메인은 그릴미 대화 중 각 섹션이 실제 맥락으로 채워졌는지 확인한다.

외부 의존 보호 항목은 product 요구사항과 대체 불가 이유를 결과 중심으로 쓴다. "그대로 / 1:1 동등 / 동일하게 / 이식 / port / parity / 마이그레이션 그대로" 같은 HOW 단어가 product 요구사항으로 들어오면 PRD 단계에서 거부한다.

## 기술 검토 필요 영역 작성 기준

PRD 초안 작성 때 아래 중 하나라도 참이면 `docs/prd.md` 의 **기술 검토 필요 영역**에 검토 질문 / PRD 근거 / 성공·실패 시 PRD 영향을 기록한다. `/tech-review` 실행 여부는 이후 Step 4 에서 이 섹션에 실제 검토 항목이 있는지로만 결정한다. 예외용 "뒤에 둬도 됨" 목록은 두지 않는다.

- 새 외부 API / SDK / model / 라이브러리 도입
- 비용, 라이선스, 성능, 품질이 MVP 성패를 좌우
- "이게 되는지"가 기능 정의 자체를 바꿀 수 있음

## 수용 기준 작성

"잘 동작" / "사용자 친화적" 같은 모호 표현은 쓰지 않는다. 통과 조건이 binary 로 판단 가능해야 한다.

| 약한 표현 | 강한 표현 |
|---|---|
| "검색이 빠르다" | "검색 결과 p95 < 200ms 응답" |
| "에러를 처리한다" | "Given 잘못된 입력, When 제출, Then 에러 메시지 X 표시 + 폼 유지" |
| "잘 보인다" | "각 카드 제목 1줄 + 메타 2줄 + 썸네일 16:9 비율" |

## AC-ID

모든 수용 기준에 안정 ID `AC-NNN` 을 박는다. `001` 부터 PRD 전역 순번이며 한번 부여하면 불변이다. 이 AC-ID 가 검증 체인의 origin 이다.

- impl 의 `REQ-NNN` 은 `(from AC-NNN)` 으로 인용한다.
- architecture-validator 는 모든 Must AC 가 1개 이상의 REQ 로 커버되는지 대조한다.
- 경로, 디렉토리 이름, 파일 포맷 같은 리터럴 규약도 별도 AC 로 명시한다.
