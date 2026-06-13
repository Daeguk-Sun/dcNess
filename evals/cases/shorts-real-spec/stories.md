# Story Backlog

## Epic — 쇼츠 템플릿 도구 (클립 → 일관 스타일 → 세로 쇼츠)

**목표**: 사용자가 가져온 짧은 영상 클립(자막 없음)에, 한 번 정해둔 일관 스타일 템플릿(세로 프레이밍 + 상단 훅 자막 + 본문 대사 자막 + 채널 워터마크)을 입혀 세로 9:16 쇼츠 한 편으로 마무리하는 도구를 만든다. 편집기는 직접 만들지 않고(클립은 미리 잘라 가져옴), repo 기존 인프라(Remotion 렌더 / ffmpeg / Streamlit 셸 / YouTube 업로드 / LLM)를 재사용해 코드 자작 경로로 브랜드 룩의 픽셀 단위 일관성을 보장한다. 저작권 판단·책임은 사람에게 두고 자동 검사는 하지 않으며 업로드 디폴트는 unlisted 로 보수적으로 간다.

**선행 조건**: v02 Epic 1(자동 영상 파이프라인) 구현·머지 완료 — Remotion 렌더 파이프라인 / ffmpeg 어댑터 / Streamlit 앱 셸 / YouTube 업로드 어댑터 / LLM 연동이 존재. 본 epic 은 그 위에 "세로 쇼츠 + 템플릿" 모드를 얹는다. 한국어 STT 정확도 검증 = GO 완료(faster-whisper large-v3 실측 CER 1.63%/WER 8.2% + 고유명사 정확) — architect-loop 진입 가능. 단 합성음 기준이라 architect 단계에서 실클립 1~2개 재확인 spike 권고.

**완료 기준** (epic 단위 수용 기준):
1. 자막 없는 클립을 올리면 한국어 STT 가 대사 자막(text + 타임스탬프) 초안을 깔고, 사용자가 교정한 자막이 최종 렌더에 반영된다.
2. 프리셋 템플릿 ≥2 개 중 택1(기본값 존재)로 작업하고, 앱 안 폼으로 새 템플릿을 만들어 영속 저장·재선택할 수 있다.
3. 동일 템플릿으로 만든 서로 다른 두 클립의 출력이 훅/자막/워터마크 타이포·위치·색에서 동일하다(= 일관성 검증, AC-532).
4. 완성 쇼츠가 1080×1920 mp4 로 export 되고, unlisted 디폴트 + `#Shorts` 로 업로드된다.
5. 영상별로 [원본 음성 유지]/[나레이션 대체] 택1이 되고, 나레이션 모드는 교정한 텍스트를 타입캐스트 TTS 로 합성해 원본 음성을 대체하며, 합성 음성 포함 시 AI 고지가 자동 반영된다.

**Base Branch:** feature/shorts-template

**GitHub Epic Issue:** [#182](https://github.com/alruminum/youTubeGenerator/issues/182)

---

### Story 1 — 클립 인테이크 + STT 자막 초안/교정

**GitHub Issue:** [#183](https://github.com/alruminum/youTubeGenerator/issues/183)

**As a** 쇼츠를 반복 생산하는 1인 운영자,
**I want** 자막 없는 클립을 올리면 대사 자막과 타이밍이 자동 초안으로 깔리고 틀린 데만 손보면 되길,
**So that** 매 영상 대사를 손으로 타이핑하는 반복 노동을 없앤다.

**영향 모듈**: `src/ports`(SpeechToTextPort 신규) + `src/adapters/stt`(Whisper 한국어 어댑터 신규 — `subprocess.run(["whisper", ...])` 로컬 실행, edge-tts/ffmpeg 패턴 동일, 무키·에이전트 미개입) + `src/core/domain`(Subtitle/SubtitleSegment 도메인) + `src/usecases`(클립 인테이크·STT 초안·교정 반영) + `app.py`(쇼츠 모드 클립 업로드 + 자막 교정 패널)

---

### Story 2 — 스타일 템플릿 시스템 (프리셋 + 폼 생성기)

**GitHub Issue:** [#184](https://github.com/alruminum/youTubeGenerator/issues/184)

**As a** 채널 룩을 일정하게 유지하려는 운영자,
**I want** 정해둔 스타일 프리셋을 골라 쓰고 앱 안에서 새 프리셋을 만들어 저장할 수 있길,
**So that** 매 영상 같은 손편집을 반복하지 않고 브랜드 룩을 픽셀 단위로 일관되게 유지한다.

**영향 모듈**: `src/core/domain`(ShortsTemplate: framing/hook_style/caption_style/watermark) + `src/ports`(TemplateStorePort) + `src/adapters/template_store`(`~/.youtubegen/shorts/templates/<name>.json` 영속) + `app.py`(템플릿 드롭다운 + "새 템플릿" 폼 + [샘플 렌더] 미리보기)

---

### Story 3 — 세로 9:16 쇼츠 렌더 + 훅 LLM

**GitHub Issue:** [#185](https://github.com/alruminum/youTubeGenerator/issues/185)

**As a** 운영자,
**I want** 클립·자막·선택한 훅·템플릿이 합쳐져 세로 쇼츠로 렌더되고 훅 문구는 LLM 이 후보를 뽑아주길,
**So that** 스크롤을 멈추게 할 훅을 매번 짜는 부담을 줄이고 완성 쇼츠를 곧장 받는다.

**영향 모듈**: `remotion/`(세로 9:16 신규 컴포지션 — 레터박스 프레이밍 + 상단 훅 + 본문 자막 + 워터마크) + `remotion/types.ts`(쇼츠 manifest) + `src/usecases/render`(세로 쇼츠 렌더 경로 — `npm run remotion:render` 로컬 실행) + `src/ports`(HookSuggestPort 신규) + `src/adapters/llm`(훅 LLM API 어댑터 신규 — 작은 직접 호출, 키 1개, v03 유일 LLM 호출) + `src/usecases`(훅 후보 생성) + `app.py`(훅 후보 픽 + 강조단어 + 미리보기/export)

---

### Story 4 — 쇼츠 업로드

**GitHub Issue:** [#186](https://github.com/alruminum/youTubeGenerator/issues/186)

**As a** 운영자,
**I want** 완성된 세로 쇼츠를 채널에 업로드하되 기본은 unlisted 이고 `#Shorts` 가 박히길,
**So that** 공개 전에 검토할 여지를 남기면서 쇼츠로 분류되어 도달을 넓힌다.

**영향 모듈**: `src/usecases`(쇼츠 업로드 메타 구성 — `#Shorts`, unlisted 디폴트, 신규 `ShortsPublishUseCase`) + `src/ports`(신규 `ShortsUploadPort`) + `src/adapters/youtube`(기존 어댑터에 `ShortsUploadPort` 구현 추가 — OAuth/미디어 helper 공유 재사용, v02 `YouTubePort`/`Meta` 경로 무변경) + `app.py`(쇼츠 업로드 폼 + Content ID 리스크 1회 안내)

---

### Story 5 — 오디오 모드 (원본 음성 유지 / 나레이션 대체)

**GitHub Issue:** [#187](https://github.com/alruminum/youTubeGenerator/issues/187)

**As a** 쇼츠를 만드는 1인 운영자,
**I want** 영상별로 원본 음성을 그대로 쓰거나, 원본을 끄고 내가 교정한 나레이션을 성우급 합성 음성으로 입힐 수 있길,
**So that** 저작권·품질 부담이 있는 원본 음성을 깔끔한 나레이션으로 대체해 채널 톤을 통일한다.

**영향 모듈**: `src/ports`(TextToSpeechPort 신규) + `src/adapters/typecast_tts`(타입캐스트 어댑터 신규 — HTTP API, 키 1개, 유료, 상업 라이선스 = 유료 plan, primary) + `src/adapters/tts`(무키 edge-tts 어댑터 — 키 없음/실패 시 자동 폴백, typecast 와 같은 `TextToSpeechPort` 독립 구현, 서로 import 안 함 = adapters_independent) + `src/adapters/llm`(나레이션 초안 — 훅 LLM 과 동일 직접 호출) + `src/core/domain`(오디오 모드 / 나레이션 도메인) + `src/usecases`(나레이션 초안·교정·TTS 엔진 선택·합성·원본 음소거 후 트랙 교체) + `remotion/`(나레이션 자막 위치 옵션 — 영상 위 / 레터박스 검은 밴드) + `app.py`(오디오 모드 선택 + 나레이션 패널) + AI disclosure(나레이션 모드 = `containsSyntheticMedia` 자동)

## 관련 이슈

| 스토리 | GitHub Issue |
|---|---|
| Epic | [#182](https://github.com/alruminum/youTubeGenerator/issues/182) |
| Story 1 | [#183](https://github.com/alruminum/youTubeGenerator/issues/183) |
| Story 2 | [#184](https://github.com/alruminum/youTubeGenerator/issues/184) |
| Story 3 | [#185](https://github.com/alruminum/youTubeGenerator/issues/185) |
| Story 4 | [#186](https://github.com/alruminum/youTubeGenerator/issues/186) |
| Story 5 | [#187](https://github.com/alruminum/youTubeGenerator/issues/187) |
