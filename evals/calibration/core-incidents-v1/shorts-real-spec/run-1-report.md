---

## SPEC_ACCEPTANCE 검수 보고

**검수 단위**: Epic — 쇼츠 템플릿 도구 (클립 → 일관 스타일 → 세로 쇼츠) / Epic Issue [#182](https://github.com/alruminum/youTubeGenerator/issues/182)

**기준 문서**: `/var/folders/.../prd.md` (PRD, AC-1 ~ AC-5) / `/var/folders/.../stories.md` (5개 Story, epic 완료 기준 5개)

**참조 기준**: [`skills/spec/spec-stories-reference.md`](skills/spec/spec-stories-reference.md) Story 분할·순서 기준

---

### 충족된 기준

**PRD Must AC ↔ epic 완료 기준 정합**: stories.md 완료 기준 1~5가 PRD AC-1~AC-5에 1:1 대응하며, 누락된 AC 항목이 없다. 각 완료 기준은 binary 판단이 가능한 서술이다.

**GitHub Issue 연결**: Epic, Story 1~5 모두 GitHub Issue 번호와 링크가 명기돼 있어 구현 문서가 원점을 인용하는 최소 추적 경로가 존재한다.

**선행 조건 명시**: v02 인프라(Remotion/ffmpeg/Streamlit/YouTube 업로드/LLM) 머지 완료와 STT 정확도 검증(faster-whisper CER 1.63%/WER 8.2%) GO 완료가 선행 조건으로 기록돼 있다.

**외부 의존 주요 항목 명기**: STT(Whisper), TTS(타입캐스트 유료 + edge-tts 폴백), LLM(훅 생성·나레이션 초안), YouTube 업로드 OAuth가 영향 모듈 항목에 구체적으로 명기돼 있다.

---

### 미충족 Gap

---

#### Gap 1 — `완료 시 확인 가능한 동작` 줄 전체 부재 (5개 Story)

`spec-stories-reference.md`는 신규 작성 stories.md에 대해 "본문은 `As a / I want / So that` + `**완료 시 확인 가능한 동작**:` 한 줄만 쓴다"고 규정하며, SPEC_ACCEPTANCE 지침은 "각 Story가 완료 시 사용자가 확인 가능한 동작 증분을 명시하는가"를 필수 판정 축으로 규정한다.

Story 1~5 본문에는 `**완료 시 확인 가능한 동작**:` 줄이 단 하나도 없다. 영향 모듈 목록(`src/ports`, `src/adapters`, `app.py` 등)이 기술되어 있으나, 이것은 구현 위치이지 사용자가 제품 경계(UI/API/CLI)에서 직접 확인하는 동작 기준이 아니다.

결과: 이후 설계/구현 단계에서 각 Story의 수용 기준을 어떤 동작 증거로 닫아야 하는지 기준이 불명확하다. STORY_ACCEPTANCE 시 AC-증거 연결 불가 위험이 높다.

**후속 분기**: stories.md를 `/spec` 수정 경로로 재작성하거나, 사용자가 각 Story에 동작 기준 한 줄을 직접 추가한다.

---

#### Gap 2 — AC-ID 불일치: stories.md `AC-532` ≠ PRD `AC-3`

PRD에는 AC-1~AC-5만 존재한다. stories.md line 12의 epic 완료 기준 3은 "동일 템플릿으로 만든 서로 다른 두 클립의 출력이 훅/자막/워터마크 타이포·위치·색에서 동일하다(= 일관성 검증, **AC-532**)"라고 기록되어 있다.

SPEC_ACCEPTANCE 지침은 "AC-ID 또는 그에 준하는 안정 참조가 있어 구현 문서가 원점을 인용할 수 있는가"를 판정 기준으로 명시한다. AC-532는 PRD에 없는 ID이므로 구현 문서가 PRD 원점을 인용할 수 없게 만드는 broken cross-reference다.

**후속 분기**: stories.md line 12의 `AC-532`를 PRD의 `AC-3`으로 정정한다.

---

#### Gap 3 — 순서 gap: 핵심 제품 약속의 첫 end-to-end 검증이 Story 4로 밀림

PRD 목표와 Must AC에서 핵심 제품 약속을 식별하면: "자막 없는 클립 → 세로 쇼츠(1080×1920 mp4) export → 업로드"이다. 이 약속의 최종 전달 경계는 AC-4의 "mp4 export + unlisted upload"이며, `spec-stories-reference.md`는 "export, upload, delivery 같은 최종 사용자 가치 경계가 있으면 그 경계가 처음 검증되는 Story를 기준으로 순서를 판단한다"고 명시한다.

현재 Story 순서에서 클립 → mp4 → 업로드의 첫 end-to-end 검증이 닫히는 위치는 Story 4다. Story 1(STT 인테이크) → Story 2(템플릿 시스템) → Story 3(렌더) → Story 4(업로드) 순서는 인테이크 레이어 → 도메인 레이어 → 렌더 레이어 → 업로드 레이어 순서로, 레이어/기능 영역 분할 순서 신호다.

지침은 "각 Story에 독립적인 하위 동작 증분이 있어도 이 순서 gap이 자동 해소되지 않는다"고 명시하며, "불가피한 사유가 epic 완료 기준 근처에 기록돼 있으면 gap 대신 warning"이라는 예외를 두지만, 현재 stories.md에는 이런 사유 기록이 없다.

Gap 1(동작 기준 줄 부재) 때문에 각 Story가 독립 동작 증분을 실제로 제공하는지도 명시적으로 확인되지 않으므로, 이 gap은 Gap 1과 함께 연동된다.

**후속 분기**:

- 최소 walking skeleton Story(클립 하나 → 고정 스타일 → mp4 렌더 → 업로드)를 Story 1~2 앞으로 올리는 순서 재배열을 검토한다.
- 또는 불가피 사유(선행 STT/템플릿 없이 렌더가 불가능한 기술 의존)가 있다면, epic 완료 기준 근처에 그 사유를 명시하면 이 gap은 warning으로 완화된다.

---

#### Gap 4 (warning) — AC-5 외부 의존(타입캐스트 TTS) 기술 검토 범위 불명확

PRD 기술 검토 섹션은 한국어 STT(faster-whisper)만 명시적으로 검증 완료로 기록하고, AC-5가 요구하는 타입캐스트 TTS API(유료, 상업 라이선스 = 유료 plan) 가용성·비용·계약 검토 완료 여부가 기록돼 있지 않다. "남은 항목 없음" 표기가 TTS를 포함하는지 불명확하다.

타입캐스트 TTS는 AC-5 전체(나레이션 대체 + AI 고지)의 핵심 외부 의존이므로, 기술 검토 미완으로 architect 단계에서 API 계약 변경이나 요금 상한 초과가 발생하면 AC-5 구현 경로가 흔들린다. 단, stories.md에 edge-tts 폴백이 명기돼 있어 완전한 단일 의존은 아니다.

이 항목은 PRD가 "남은 항목 없음"을 의도적으로 TTS를 포함해 기록한 것인지, 아니면 누락인지를 현재 읽기 전용으로는 판단할 수 없으므로 warning으로 보고한다.

**후속 분기**: PRD 기술 검토 섹션에 타입캐스트 TTS 검증 결과(API 가용성, 상업 플랜 비용, 대안 폴백 충분성)를 명시하거나, architect 단계에서 spike로 분리한다.

---

### 보고 요약

| # | 분류 | 내용 | 후속 |
|---|---|---|---|
| 1 | **FAIL gap** | 5개 Story 모두 `완료 시 확인 가능한 동작` 줄 없음 | `/spec` 수정 재작성 |
| 2 | **FAIL gap** | AC-532 ≠ PRD AC-3 broken cross-reference | stories.md line 12 정정 |
| 3 | **FAIL gap** | 핵심 end-to-end(export+upload) 검증이 Story 4로 밀림, 불가피 사유 기록 없음 | 순서 재배열 또는 사유 명시 |
| 4 | **warning** | 타입캐스트 TTS 기술 검토 범위 불명확 | PRD 기술 검토 보완 또는 architect spike |

---

**FAIL**

Gap 1(동작 기준 줄 전체 부재), Gap 2(AC-ID broken cross-reference), Gap 3(순서 gap, 불가피 사유 기록 없음)가 SPEC_ACCEPTANCE 필수 판정 기준 미충족으로 확인됐다. 이후 설계/구현 단계 진입 전 stories.md를 수정해야 한다.
