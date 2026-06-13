# 정답표 — 계약 수준 (L3 실사고 케이스)

출처: youTubeGenerator v03 epic-01-shorts-template 의 실제 stories.md. 옛 지침은 이 backlog 를 통과시켰고, 실제로 핵심 동작 검증이 Story 3 까지 밀려 런타임 gap(youTubeGenerator #214)이 났다. 본 케이스는 지금 고친 story 분할·순서 축이 이 실데이터를 잡는지 회귀로 보존한다.

검수 보고를 채점할 때 아래 기대만 본다. 어떤 검수자가 어떤 문구로 말했는지, gap 이 몇 개인지는 채점하지 않는다.

이 케이스가 보호하는 깨끗한 신호는 **순서 축**이다 — 핵심 약속(완성 세로 쇼츠)의 첫 동작 검증이 뒤 story 까지 밀린 것이 실제 사고(youTubeGenerator #214 "Story 3 제품 검수 런타임 gap")의 설계단 원인이다. (참고: 이 실 backlog 는 각 story 가 app 화면 하위 동작을 일부 내므로 "앞 story 에 동작이 전무하다"는 식의 행동적 분할 주장은 경계선이라 MUST 로 두지 않는다. 옛 양식이라 `완료 시 확인 가능한 동작` 줄 부재 자체도 단독 결함이 아니다.)

- [E1][MUST] 보고가 "핵심 약속인 완성 세로 쇼츠의 첫 end-to-end 동작 검증이 앞 story 가 아니라 뒤 story(렌더 story 이후)까지 밀린다"는 취지의 순서 결함을 지적한다.
- [E2][MUST] 최종 결론이 통과(PASS)가 아니다.
