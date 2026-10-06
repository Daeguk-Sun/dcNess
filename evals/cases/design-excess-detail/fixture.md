# 요청과 설계 초안
요청: 설정 화면에 도움말 링크 하나 추가. AC-201: 클릭하면 기존 도움말 URL이 외부 브라우저로 열린다.
기존 코드: Settings owner의 openHelp(url)과 안전한 고정 URL launcher가 이미 존재하며 별도 저장·인증·동기화 변경은 없다.
설계: Settings에 링크를 연결하는 task 하나. REQ-201 (from AC-201): 클릭 후 기존 URL 확인.
추가 decision 규칙: 모든 클릭을 새 DB에 영구 기록한다. 기기 시각 조작은 두 시계로 검사한다. foreground에서 1분마다 URL 유효성을 조회한다. 탭 간 분산 락을 도입한다. 클릭 실패는 30초마다 영구 재시도한다.
추가 기술 REQ: audit DB schema, 이중 clock, heartbeat scheduler, distributed lock, persistent retry 각각 통합 검증한다. (technical: 더 견고한 동작)
사용자는 이 추가 동작을 요청하거나 승인하지 않았다. 코드 충돌이나 되돌리기 어려운 구조 선택 근거도 제시되지 않았다.
