# 확정 계약과 위임
사용자 확정: 읽기 전용 FAQ 화면에서 제목으로 로컬 정적 목록을 필터링한다. AC-301: 입력한 제목이 포함된 FAQ만 표시한다.
기존 코드: FaqFilter pure function이 동기적으로 목록을 계산한다. 저장·권한·네트워크·공유 mutable state가 없다.
구조: FaqPanel이 입력 state와 rendering을 소유하고 FaqFilter를 호출한다. 첫 task 하나가 전체 UI 동작을 연결한다. 의존 방향은 UI → pure filter다.
REQ-301 (from AC-301): 기존 test command `python -m unittest tests.test_faq`로 일치·불일치·빈 입력을 검증한다. Scope는 faq owner 코드와 대응 테스트다. 계약 사본 없이 위 동작을 참조한다.
설계 agent 결정: 같은 이벤트 루프에서 빠르게 입력이 바뀔 때 내부 재계산 방식은 구현자에게 위임한다. 최종 입력에 맞는 결과와 동기 pure filter 경계를 지키고, debounce·worker·저장·새 제품 정책을 추가하지 않는다. 별도의 타이밍 숫자는 고정하지 않는다.
다른 계약은 이번 검토에서 이미 통과했다. 이 위임의 적정성을 판정하는 delta 검토다.
