# 계약 변경과 재배치

## CONTRACT_AMENDMENT

module-architect가 public contract를 만들거나 바꾸면 같은 작업 안에서 다음 두 곳만 갱신한다.

- epic `architecture.md` 의 `## 모듈 목록`: 책임 / 공개 인터페이스 / 검증 경로 칸에 불변조건, forbidden append, owner, validation path 를 한 줄로 남긴다.
- `docs/decisions/NNNN-slug.md`: 왜 이 계약이 필요한지, 버린 대안, ordering/error/config 같은 긴 사유와 규칙을 기록한다.

impl 문서는 관련 `module:` 과 `decision:` id/link 만 가리킨다. invariant, ordering, error mode, config, forbidden alternative 전문을 다시 쓰지 않는다. 구양식 Contract Ledger / Contract References 산출물은 기존 활성 프로젝트 호환 reader의 입력으로만 유효하며 신규 산출물에는 만들지 않는다.

변경 보고에는 다음을 포함한다.

- 바뀐 contract 의미
- owner module
- 변경 전 값
- 변경 후 값
- 영향을 받는 consumer
- 갱신한 decision id/link
