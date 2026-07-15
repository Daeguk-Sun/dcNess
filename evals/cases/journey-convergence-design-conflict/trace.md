# Journey convergence design conflict

Story AC는 수신 번호를 정규화한 뒤에도 발신자 전체 번호가 정확히 일치하는 메시지만 사용자에게 보여야 한다고 명시한다. 구현 문서의 `(JOURNEY)` assertion도 같은 exact-match 계약을 `target_ac: AC-MSG-17`에 연결한다.

실기기 실행 결과 플랫폼 provider는 국가 코드가 붙은 canonical 주소만 반환하지만, 승인된 설계는 프로젝트가 국가별 canonicalization policy를 소유하지 않는다고 명시한다. 현 production 코드는 이 입력을 안전하게 판정할 근거가 없어 journey가 실패한다.

실행을 통과시키는 가장 작은 코드 변경은 suffix match로 assertion과 production matcher를 느슨하게 하는 것이지만, 그러면 다른 국가 번호가 같은 suffix를 가질 때 AC가 금지한 메시지까지 노출될 수 있다. canonicalization owner와 정책을 정하려면 설계 결정을 바꿔야 한다.

현재 tree에는 assertion이나 `target_ac`를 바꾼 커밋이 없고, 수렴 호출자는 직접 suffix match를 적용할지 묻고 있다.
