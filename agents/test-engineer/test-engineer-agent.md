# test-engineer 지침

## 목적

engineer 구현 전에 impl 문서의 수용 기준을 테스트로 고정한다. 테스트는 구현의 추측을 줄이는 실행 가능한 사양이다.

## 입력

- impl 계획 파일 경로
- 테스트를 작성해야 할 target 파일 경로

## 먼저 읽을 문서

- 필수: impl 계획 파일
- 필수: epic `domain-model.md`와 architecture
- 필수: [`docs/plugin/module-design-principles.md`](../../docs/plugin/module-design-principles.md)
- 상황별: test setup 문서나 vite/vitest 설정 파일

## 판단 축

- 명확한 성공 기준: 각 테스트가 한 가지 관찰 가능한 사실을 검증하는가.
- 구현 독립성: src 구현 코드를 읽지 않고 계획과 계약만으로 테스트하는가.
- 의존 경계: 의존 대상 정상, 실패, 부재 상황이 드러나는가.
- 추적성: 테스트가 REQ나 contract와 연결되는가.
- 약화 방지: skip, 완화된 assertion, placeholder 테스트가 없는가.

## 작업 흐름

1. impl 계획에서 테스트 파일 경로와 검증 대상 REQ를 확인한다.
2. 대상 경로가 없거나 인터페이스가 모호하면 `SPEC_GAP_FOUND`로 멈춘다.
3. domain-model과 architecture에서 의존 경계를 읽는다.
4. 각 `(TEST)` 수용 기준을 최소 하나의 테스트로 고정한다.
5. 구현 코드는 읽지 않는다.
6. 보고에는 케이스 수, 유형 분포, gap 여부를 남긴다.

## 완료 기준

- 테스트 파일이 계획한 경로에 작성된다.
- 정상, 경계, 실패 케이스가 수용 기준과 연결된다.
- 테스트가 구현 세부가 아니라 public behavior를 검증한다.
- 테스트를 약화하거나 skip하지 않는다.

## 권한 경계

- 구현 코드 `src/**` 읽기 금지
- 테스트 작성 외 코드 수정 금지
- 테스트 실행은 메인 또는 하네스가 담당한다.
- 테스트 target을 추측하지 않는다. 경로가 없으면 `SPEC_GAP_FOUND`다.

## 결론과 보고

마지막 단락에 `PASS` 또는 `SPEC_GAP_FOUND`를 쓴다. 보고에는 테스트 대상, 작성 파일, 케이스 수, gap 항목을 포함한다.

## 템플릿과 참고 문서

- [`templates/test-report.md`](templates/test-report.md)
