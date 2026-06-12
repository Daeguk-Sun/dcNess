# architecture-validator finding 예시

이 문서는 checklist가 아니라 예시 카탈로그다. 여기에 없는 결함도 판단 축에 걸리면 finding으로 쓴다.

## 요구사항 출처 충실도

- PRD Must AC가 impl REQ에 인용되지 않음
- PRD의 경로, 파일명, 포맷 리터럴이 impl에서 바뀜
- 문서끼리는 일치하지만 PRD와 다른 self-consistent wrong 상태

## 설계 표준

- architecture에 의존 그래프는 있지만 실제 차단 방법이 없음
- 모듈 공개 API가 내부 파일 import를 전제함
- DI가 필요하지만 생성자나 인자 주입 경로가 설명되지 않음

## 계약과 인터페이스

- Contract Ledger가 signature만 적고 invariant가 없음
- producer와 consumer가 같은 contract 이름을 다른 의미로 씀
- forbidden alternative가 없어 stale 구현을 막을 근거가 없음

## 구현 가능성

- impl 문서가 실패 경로를 설명하지 않아 engineer가 임의 정책을 정해야 함
- 선행 task가 없는데 이미 생성된 데이터로 가정함
- 수용 기준이 실행 가능하거나 관찰 가능한 조건으로 닫히지 않음

## 제품 동작 슬라이스

- Story impl 이 ports / adapter / usecase 같은 레이어별 부품 task로만 나뉘고, Story 완료 시 실제로 검증되는 사용자/API/CLI 동작이 어느 task 또는 task 묶음 책임인지 비어 있음
- 병렬 파일 경계를 맞추느라 한 제품 흐름의 입력, 처리, 출력이 서로 독립 task처럼 분리됐지만 `depends_on` 과 첫 동작 증거 지점이 없음
- 첫 제품 경계 동작이 마지막 task까지 밀렸는데 왜 앞당길 수 없는지와 후속 검증 방법이 없음
- `Story 동작 슬라이스` 섹션은 있지만 "추후 통합에서 확인" 같은 추상 문구만 있고 실제 제품 경계나 검증 명령이 없음
- cross-story 통합 검증에서 각 task 는 PASS 했지만 Story 간 compose/wiring 으로 열리는 사용자 흐름의 첫 동작 증거가 어디에도 없음

## drift와 scope

- root ADR과 epic ADR의 같은 결정이 다름
- Contract Ledger는 갱신됐지만 impl 문서에 이전 consumer가 남음
- 특정 task만 수정하면 되는데 system 재설계로 끌어올릴 위험이 있음

## 표현 수준

- private helper 이름을 강제함
- loop body나 try/catch 흐름이 긴 code block으로 들어감
- 테스트 함수명을 지정해 구현과 테스트 구조를 선점함
