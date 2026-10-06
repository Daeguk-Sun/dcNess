# 사용자 대화와 설계 발췌
사용자: 화면이 뒤로 내려가고 30분이 지나 앞으로 올라오면 토큰을 갱신한다.
메인 PRD 편집: 위 문장 뒤에 "프로세스 종료 여부는 결과를 바꾸지 않는다. 기준은 시간뿐이다"를 추가했다. 이에 대한 사용자 응답은 없다.
Story AC-101: background 진입을 관찰한 후 30분이 지나 resume하면 갱신한다.
기존 코드: lifecycle adapter가 background timestamp를 저장하고 resume에서 token service를 호출한다. 프로세스가 foreground에서 강제 종료될 때 마지막 시각은 기록하지 않는다.
결정 초안: 기존 background/resume 경로만 유지한다. 비정상 종료 후에는 기존 로그인 복구 정책을 따른다.
직전 검증: PRD와 충돌하므로 foreground 연속 사용 중 매분 timestamp를 영구 저장하도록 보강해야 한다.
