# impl-validator finding class

`impl-validator` 의 FAIL finding 은 재진입 모드를 보존하기 위해 class 를 붙인다. finding 은 항상 merge candidate diff 기준이다. 다중 story/epic invocation에서는 개별 PR 단편이 아니라 stack tip vs main diff에서 드러나는 cross-story 결함도 같은 class로 분류한다.

## spec-gap

구현 로직이나 범위가 계획 계약과 어긋난 경우다. 하나라도 있으면 build-worker rework 또는 설계 보강이 우선이다.

- 계획한 public interface, data shape, error behavior 와 구현이 다름
- 계획 밖 기능이나 파일이 섞임
- domain invariant, architecture, design token, DB schema 계약 위반
- design:required UI 계획이 요구한 디자인 토큰 적용 누락 또는 boilerplate 색 상수 잔존
- bugfix 원인이 남아 있거나 주변 동작을 깨뜨림
- 테스트가 계획한 contract 를 검증하지 못하고 구현이 그 gap 에 의존함

## quality-gap

계획 계약은 대체로 맞지만 merge blocker 수준의 유지보수·운영 위험이 있는 경우다. quality-gap 만 있으면 메인 root-cause 수정 또는 build-worker rework 로 보낸다.

- 과한 추상화, 읽기 어려운 분기, 의미 있는 중복
- debug 잔재, hardcode, cleanup 누락, async ordering 위험
- 목업과 다른 default palette, boilerplate 색 상수 잔존, 정당화 없는 디자인 토큰 적용 누락
- 코드 패턴으로 확인 가능한 보안 위험
- owner module 없이 entrypoint/session/global state 에 새 흐름을 흡수
- PR 범위 안에서 기존 장기 문서를 stale 하게 만듦

### Agent Operability MUST FIX 승격

UI/API/CLI entrypoint 를 만지는 diff 는 새 flow append 인지, owner module 이 있는지, entrypoint 가 dispatch-only entrypoint 로 남는지, entrypoint 가 render/helper/session/global state 를 함께 흡수하는지, owner 근처 validation path 가 있는지 확인한다.

owner module 없이 새 mode/screen/panel/flow 를 entrypoint 에 append 하면서 render/helper/session/global state 를 함께 흡수하고 owner 근처 validation path 를 남기지 않으면 NICE TO HAVE 가 아니라 MUST FIX 로 승격한다. 이는 edit target, state owner, validation path 를 동시에 흐리는 overly broad entrypoint 문제다.

entrypoint 파일 자체는 owner module 로 인정하지 않는다. 함수명 prefix 는 searchability 보조 신호일 뿐 owner 분리 증거가 아니다. manual-only validation 은 owner 근처 validation path 가 아니다. footprint 밖 기존 누적은 후속 권고로 둔다.

## mixed

`spec-gap` 과 `quality-gap` 이 섞이면 `spec-gap` 우선이다. 설계 계약과 어긋난 변경은 단순 품질 보정으로 닫지 않는다.
