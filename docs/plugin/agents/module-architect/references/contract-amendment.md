# 계약 변경과 재배치

## CONTRACT_AMENDMENT

module-architect가 public contract를 만들거나 바꾸면 같은 작업 안에서 다음 두 곳만 갱신한다.

- epic `architecture.md` 의 `## 모듈 목록`: 책임 / 공개 인터페이스 / 검증 경로 칸에 불변조건, forbidden append, owner, validation path 를 한 줄로 남긴다.
- `docs/decisions/NNNN-slug.md`: 왜 이 계약이 필요한지, 버린 대안, ordering/error/config 같은 긴 사유와 규칙을 기록한다.

impl 문서는 관련 `module:` 과 `decision:` id/link 만 가리킨다. invariant, ordering, error mode, config, forbidden alternative 전문을 다시 쓰지 않는다. 구양식 Contract Ledger / Contract References 산출물은 기존 활성 프로젝트 호환을 위해 유효하지만, 신규 산출물이나 이번에 수정하는 산출물은 module/decision 참조로 축소한다.

변경 보고에는 다음을 포함한다.

- 바뀐 contract 의미
- owner module
- 변경 전 값
- 변경 후 값
- 영향을 받는 consumer
- 갱신한 decision id/link
- 구양식 Ledger/References 를 건드렸다면 legacy sync 위치

## LEGACY_CONTRACT_SYNC

구양식 Contract Ledger 또는 Contract References 가 남아 있어도 형식만으로 FAIL 하지 않는다. 다만 이번 변경이 그 계약 의미를 실제로 수정한다면, stale 사본이 되지 않도록 해당 줄을 module/decision 참조로 축소하거나 경계 밖 stale 위치를 보고한다.

legacy sync 에서는 다음만 한다.

- 신규 진본인 module row 와 decision 문서를 확인한다.
- write 경계 안의 구양식 전문 사본을 module/decision 참조로 줄인다.
- write 경계 밖 stale 은 위치를 보고한다.
