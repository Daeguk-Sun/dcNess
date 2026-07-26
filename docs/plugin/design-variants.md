# 디자인 변형 산출물 계약

> `docs/design-variants/`의 구조·진본·생성·검사 계약 SSOT. 실행 wrapper는 [`../../skills/canvas-design/SKILL.md`](../../skills/canvas-design/SKILL.md)다.

## 북극성

디자인 산출물은 프로젝트 종류와 무관하게 두 질문에 답한다.

- 저니 보드: 사용자가 한 여정에서 어떤 경로로 다니는가
- 변형 전수 보드: 화면이 어떤 모양과 변형을 갖는가

사람의 역할은 agent가 제시한 후보의 PICK과 생성 결과 검수다. 화면·여정·배치 값을 사람이 산출물에 옮겨 적지 않는다.

## 구조

```text
docs/design-variants/
├── index.html
├── README.md
├── boards/
│   ├── journey-<journey-id>.html
│   └── screen-states.html
├── screens/
├── drafts/
└── _lib/
```

| 영역 | 역할 | 소유 |
|---|---|---|
| `screens/` | 화면별 확정본. 화면 그림의 유일한 진본 | designer 후보를 PICK한 뒤 메인이 순수 이동 |
| ux-flow | 화면 인벤토리·전이 개요·여정 선언의 진본 | 설계 단계 agent, 사람 승인 |
| `boards/` | 저니 N개와 변형 전수 1개 | 생성기 |
| `README.md` | cold-start agent용 전체 좌표 | 생성기 |
| `index.html` | 사람용 두 갈래 입구 | 생성기 |
| `drafts/` | PICK 대기 후보 | designer |
| `_lib/` | 서비스 공통 보드 엔진 | plugin 배포본 |

보드와 진입점은 화면 사본이나 자체 계약을 소유하지 않는다. 모든 생성물에는 재생성 명령, 진본 경로, 진본 해시가 들어간다.

## 화면 확정본

- 파일은 `screens/<screen-id>.html`이며 버전 접미사를 쓰지 않는다.
- 모든 변형 블록은 고유한 `data-variant`를 갖는다.
- 변형 축이 있으면 같은 블록의 `data-variant-values`에 `축=값` 쌍을 선언한다. 축 이름과 값 체계는 프로젝트가 정한다.
- 첫 축은 전수 보드의 열, 둘째 축은 행, 나머지는 facet으로 파생한다.
- `_lib/only-variant.js`, `_lib/report-size.js`, `_lib/show-ids.js`를 참조한다.
- `#only=<variant>`가 없는 값을 가리키면 눈에 보이는 경고를 표시한다.

크기는 확정본이 부모 보드에 보고한다. 파일 안의 보드 크기 선언은 진본이 아니다.

designer는 PICK 설명을 HTML 밖의 보고에 둔다. 확정본 형식을 바꾸는 draft 전용 마커나 `draft N` 라벨을 HTML에 넣지 않는다. 승격은 같은 깊이의 `drafts/`에서 `screens/`로 이동하는 것으로 끝나며, 같은 화면의 탈락 후보만 제거한다.

## 여정 선언

ux-flow는 전이 개요를 한 번만 소유한다. 여정 경로는 개요 전이를 순서대로 가리키며 라벨을 복제하지 않는다. 같은 화면쌍에 전이가 여러 개일 때만 라벨 일부로 구분한다.

프로젝트는 ux-flow 안의 `dcness-journey-contract` JSON으로 다음을 선언한다.

- 여정 단위
- 여정 절을 찾는 정규식의 `id` named group
- 이름 소스의 path와 읽기 방식

이름 소스는 표 또는 heading 패턴을 사용할 수 있다. 따라서 스토리, 사용자 목표, URL 흐름, 대화 시나리오가 같은 생성기를 쓴다. 생성기에 `Story N` 같은 프로젝트 관례를 넣지 않는다.

```json dcness-journey-contract
{
  "unit": "user-goal",
  "journeyHeadingPattern": "^Goal (?<id>[a-z0-9-]+)$",
  "nameSource": {
    "kind": "table",
    "path": "ux-flow.md",
    "section": "여정 카탈로그",
    "idColumn": "여정 ID",
    "nameColumn": "이름"
  }
}
```

선언된 여정마다 확정본 사이 전이가 두 개 이상 남으면 보드를 만든다. 확정본 없는 화면의 전이는 사유와 함께 제외한다. 남은 전이가 부족한 여정은 보드와 사람용 카드를 만들지 않고 두 진입점에 사유를 남긴다.

노드는 선언 경로에서 마지막으로 등장한 순서로 놓는다. 같은 화면을 여러 여정이 참조해도 `screens/` 파일은 하나다. 위치·간격·곡률은 보드 파일에 기록하지 않고 엔진이 경로와 렌더 결과에서 파생한다.

## 생성과 검사

생성기는 plugin이 소유하며 프로젝트로 복제하지 않는다.

| 생성기 | 소유 산출물 |
|---|---|
| `scripts/design/build-journey-boards.mjs` | `boards/journey-*.html` 생성·삭제 |
| `scripts/design/build-screen-states.mjs` | `boards/screen-states.html` |
| `scripts/design/build-design-index.mjs` | `README.md`, `index.html`, 프로젝트 문서의 포인터 한 줄 |
| `scripts/design/ux-flow.mjs` | 세 생성기의 공용 모델 |

각 생성기는 project root와 대상 ux-flow를 입력받고 `--check`에서 현재 산출물과 재생성 결과를 비교한다. ux-flow 또는 screen 변경 경로는 세 생성과 세 검사를 함께 수행한다. doc-sync CI도 같은 검사를 실행한다.

검사는 다음 drift를 조용히 넘기지 않는다.

- 여정 선언과 보드 파일 목록 불일치
- 개요에 없는 전이 또는 모호한 병렬 전이
- 확정본 없는 화면과 제외 사유
- 변형 마커 누락·중복·축 값 누락
- 확정본의 draft 전용 메타와 같은 화면의 잔여 후보
- 보드·진입점의 진본 해시 불일치

## 엔진 배포

seed는 엔진 4파일, 빈 변형 전수 보드, `.gitignore`, `drafts/.gitkeep`만 제공한다. 저니 보드와 두 진입점은 프로젝트 진본을 읽은 뒤 생성한다.

프로젝트는 `_lib/`를 수정하지 않는다. 생성기는 배포본과 다른 엔진을 경고하되 자동 덮어쓰지 않는다. 갱신은 canvas-design에서 명시적으로 수행한다. 기존 단일 `canvas.html` 프로젝트는 강제 마이그레이션하지 않으며, 새 계약으로 전환할 때만 새 구조를 생성한다.

## 진입점

`README.md`는 한 파일만 읽어도 화면·변형·전이·여정·보드·미생성 사유·진본과 파생 관계·draft 의미를 알 수 있게 한다. `index.html`은 같은 모델을 사람용 여정/화면 두 갈래로 표현한다.

프로젝트 `CLAUDE.md`와 `docs/index.md`는 `docs/design-variants/README.md`를 가리키는 포인터만 둔다. 생성 진입점에 계약을 손으로 추가하지 않는다.
