# 보강 입력
사용자 확정: 앱이 background로 내려갈 때 저장한 시각부터 30분이 지나 resume하면 토큰을 갱신한다. 기존 강제 종료 복구 정책은 유지한다.
코드: LifecycleAdapter → TimestampStore → ResumeHandler → TokenService 경로가 있고 background 저장과 resume 비교의 owner/scope는 닫혀 있다.
메인이 추가한 PRD 문장: foreground에서 갑자기 종료돼도 시간만으로 항상 동일 결과를 보장한다. 사용자 합의는 없다.
검증 지적: 연속 foreground 사용 중 crash를 완전히 복구하려면 주기적으로 시각을 써야 한다.
보강 후보: foreground 동안 1분마다 storage write를 수행하는 scheduler를 신규 설계한다.
이번 호출은 위 보강을 결정 문서에 반영할지 판단하는 단계다. 읽기 전용 eval이므로 실제 수정 대신 처리와 이유를 보고한다.
