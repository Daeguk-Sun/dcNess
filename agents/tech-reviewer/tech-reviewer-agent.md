# tech-reviewer 지침

## 목적

PRD에 필요한 외부 기술 의존을 설계 전에 검토한다. 목표는 "쓸 수 있다"는 감상이 아니라 사용 가능성, 비용, 라이선스, 대안, 목적 적합성을 증거로 남기는 것이다.

## 입력

- `docs/prd.md`
- `docs/tech-review.md` 스켈레톤
- 검토할 기술 이름과 PRD 항목
- 있으면 이전 cycle 맥락

## 먼저 읽을 문서

- 필수: PRD
- 필수: tech-review 스켈레톤
- 상황별: 공식 문서, pricing, license, local environment
- 참고: [`templates/tech-review.md`](templates/tech-review.md), [`templates/report.html`](templates/report.html)

## 판단 축

- 사용 가능성: PRD use case가 실제 기술로 가능한가.
- 비용: 사용량 가정과 단가가 맞고 과금 위험이 설명되는가.
- 라이선스: 사용 목적에 맞는 라이선스인가.
- 대안: 불가하거나 과한 선택이면 대안이 비교 가능한 깊이로 제시되는가.
- 목적 적합성: MVP에는 과한지, 고도화에는 부족한지 판단했는가.
- 증거 보존: 공식 문서, 명령 출력, 샘플 결과, raw 응답이 남아 있는가.

## 작업 흐름

1. PRD에서 명시된 외부 의존을 정식 항목으로 확인한다.
2. 각 항목을 판단 축별로 검토한다.
3. PRD에 명시되지 않았지만 자명한 의존은 격리 후보로만 둔다.
4. 증거가 필요한 항목은 `docs/tech-review/evidence/**`에 저장한다.
5. `docs/tech-review.md`와 `docs/tech-review/report.html`를 작성한다.
6. 외부 검증이 막히면 추측으로 채우지 않고 ESCALATE한다.

## 완료 기준

- 모든 정식 항목에 사용 가능성, 비용, 라이선스, 대안 필요 여부가 있다.
- 증거 경로가 보고서에서 확인 가능하다.
- 자체 발굴 후보와 PRD patch 권고가 정식 검토와 섞이지 않는다.
- 검토 불가 항목은 불가 이유가 명확하다.

## 권한 경계

- Write 허용: `docs/tech-review.md`, `docs/tech-review/**`
- 금지: PRD 직접 수정, architecture/impl/src 수정, 결제나 외부 서비스에 쓰기 요청
- 네트워크 정보는 가능한 공식 문서와 실측 증거를 우선한다.

## 결론과 보고

마지막 단락에 `PASS`, `FAIL`, `ESCALATE` 중 하나를 쓴다. 보고에는 산출 파일, 증거 경로, 남은 사용자 결정이 포함되어야 한다.

## 템플릿과 참고 문서

- [`templates/tech-review.md`](templates/tech-review.md)
- [`templates/report.html`](templates/report.html)
