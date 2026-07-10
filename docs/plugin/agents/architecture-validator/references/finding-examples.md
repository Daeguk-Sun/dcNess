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

- module responsibility 가 signature만 적고 invariant가 없음
- producer와 consumer가 같은 module/decision 참조를 다른 의미로 씀
- forbidden alternative가 decision 문서에 없어 stale 구현을 막을 근거가 없음
- 신규 산출물의 impl 문서가 module/decision 참조 대신 invariant/ordering/error mode 전문 사본을 다시 적음
- 구양식 Contract Ledger / Contract References 가 남아 있지만 이번 변경과 무관한 형식 잔존뿐임 (Should, Must 아님)

## 고위험 상태 계약

- 진본(외부 Provider/시스템)과 mirror 의 reconcile 이 identity 존재 여부와 일부 필드만 비교해, 같은 identity 의 가변 상태 변경(예: 발신 상태 전이)이 mirror 에 반영되지 않음
- "observer 가 수렴한다" 같은 추상 문구만 있고 그 수렴을 구현하는 update 경로, owner, task scope 가 어디에도 없음
- 뒤 Story 가 소비하는 상태 전이를 앞 Story 의 저장·동기화 계약이 수용하지 못하는데 어느 task 도 그 gap 을 수정할 scope 가 없음
- source 일부 read 실패를 empty 와 같게 취급해 기존 mirror 상태가 삭제됨
- 같은 snapshot 반복 실행이 no-change 로 닫히는지 어디에도 없음

## 구현 가능성

- impl 문서가 실패 경로를 설명하지 않아 build-worker가 임의 정책을 정해야 함
- 선행 task가 없는데 이미 생성된 데이터로 가정함
- 수용 기준이 실행 가능하거나 관찰 가능한 조건으로 닫히지 않음

## 제품 동작 슬라이스

- Story impl 이 ports / adapter / usecase 같은 레이어별 부품 task로만 나뉘고, Story 완료 시 실제로 검증되는 사용자/API/CLI 동작이 어느 task 또는 task 묶음 책임인지 비어 있음
- 병렬 파일 경계를 맞추느라 한 제품 흐름의 입력, 처리, 출력이 서로 독립 task처럼 분리됐지만 `depends_on` 과 첫 동작 증거 지점이 없음
- 첫 제품 경계 동작이 마지막 task까지 밀렸는데 왜 앞당길 수 없는지와 후속 검증 방법이 없음
- `Story 동작 슬라이스` 섹션은 있지만 "추후 통합에서 확인" 같은 추상 문구만 있고 실제 제품 경계나 검증 명령이 없음
- final epic 검증에서 각 task 는 PASS 했지만 Story 간 compose/wiring 으로 열리는 사용자 흐름의 첫 동작 증거가 어디에도 없음

## 구현 순서

- epic architecture 의 구현 순서가 인프라/부품 모듈을 전부 만든 뒤에야 첫 사용자 동작이 나오게 정렬됐는데 사유와 경고가 없음
- 의존 그래프와 구현 순서 설명은 있지만 어느 시점에 첫 제품 경계 동작이 검증되는지 어디에도 없음

## drift와 scope

- 전역 decision 과 epic architecture 의 같은 결정이 다름
- decision 은 갱신됐지만 impl 문서에 이전 consumer가 남음
- module responsibility 는 갱신됐지만 impl 문서의 module/decision 참조가 이전 의미를 가리킴
- 특정 task만 수정하면 되는데 system 재설계로 끌어올릴 위험이 있음

## 표현 수준

- private helper 이름을 강제함
- loop body나 try/catch 흐름이 긴 code block으로 들어감
- 테스트 함수명을 지정해 구현과 테스트 구조를 선점함
