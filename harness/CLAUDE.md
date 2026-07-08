# harness 모듈 안내

전역 작업 규칙은 [../CLAUDE.md](../CLAUDE.md)가 진본이다. 이 파일은 `harness/` 안에서
어디를 먼저 볼지 좁혀 주는 컴퍼스다.

## 소유 범위

- Claude Code hook 핸들러, run/session 상태, file boundary, agent routing, validation prose
  I/O를 담당하는 플러그인 런타임 코드.
- 외부 활성 프로젝트에서 실제로 실행되는 보호 장치이므로 dcness self 에서 통과해도 사용자
  프로젝트에서의 경로와 상태 파일을 같이 생각해야 한다.
- 비용/효율 측정, guard telemetry, parallel wave, merge lock 같은 운영 보조 상태도 이 모듈에
  모여 있다.

## 먼저 볼 파일

- [hooks.py](hooks.py): SessionStart, PreToolUse, PostToolUse, Stop 계열 hook 진입점.
- [session_state.py](session_state.py)와 [session_state_cli.py](session_state_cli.py):
  harness-state의 session/run/live 상태 진본.
- [agent_boundary.py](agent_boundary.py): sub-agent Read/Write/Bash/MCP mutation 경계.
- [signal_io.py](signal_io.py): validator/reviewer 결과 prose 파일 I/O.
- [agent_routing.py](agent_routing.py), [agent_names.py](agent_names.py): agent 명칭 정규화와
  provider/routing 판정.
- [merge_lock.py](merge_lock.py), [parallel_wave.py](parallel_wave.py),
  [wave_board.py](wave_board.py): 병렬 작업과 merge 순서 보호.
- [context_docs.py](context_docs.py): 활성 프로젝트 `CLAUDE.md` seed, migration, audit helper.
- [efficiency/](efficiency/): 세션 비용과 반복 패턴 분석 도구.

## 수정 시 주의점

- hook 계열은 기본적으로 fail-open이다. 명시적 catastrophic 위반만 block 하고, payload 파싱 실패나
  상태 파일 손상은 사용자 작업을 멈추지 않게 처리한다.
- harness-state 파일은 runtime interface다. schema를 바꾸면 기존 run/state를 읽는
  경로와 cleanup 경로를 같이 본다.
- `signal_io.py`는 prose 중심 I/O만 맡는다. marker line, status JSON, schema 강제 패턴을 되살리지
  않는다.
- boundary/routing 변경은 외부 활성 프로젝트의 작업 가능 영역을 바꾼다. 관련 agent 문서,
  `docs/plugin/**`, 테스트가 같이 맞는지 확인한다.
- subprocess probe는 shell 없이 argv와 timeout을 우선 사용한다. hook에서 hang 나면 전체 UX가
  느려진다.

## 검증

- 좁은 변경은 대응 테스트를 먼저 고른다. 예: boundary는 [../tests/test_agent_boundary.py](../tests/test_agent_boundary.py),
  hook은 [../tests/test_hooks.py](../tests/test_hooks.py), context docs는
  [../tests/test_context_docs.py](../tests/test_context_docs.py).
- 범위가 불명확하면 `python3.11 -m unittest discover -s tests -v < /dev/null`로 전체 unit suite를
  돌린다.
- 보안성 있는 경계, subprocess, 파일 권한 변경은 static-quality gate까지 확인한다.
