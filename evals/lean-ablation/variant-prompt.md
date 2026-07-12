현재 디렉터리의 파일만 읽고 `route_message`의 현재 runtime entrypoint, capability
owner 파일, stale 경로를 판정한다. `registry.json`의 등록과 실제 구현을 근거로
응답한다. 파일을 수정하지 않는다.

제품 AC:

1. `entrypoint`가 `src/runtime.py::dispatch`다.
2. `owner`가 `src/runtime.py`이고 `stale_path`가 `legacy/router.py`다.

[LESSONS: system-architect]
- `TOOL_REPEAT_HIGH`: 같은 tool/input 반복 호출을 멈추고 첫 결과를 재사용한다. 재확인은 grep, offset, 더 좁은 입력으로 수행한다.
