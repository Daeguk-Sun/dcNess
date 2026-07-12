# Next design — scheduled attachment export

다음 epic은 기존 attachment export를 nightly scheduler에서 호출한다.

- Codebase Sanity receipt preflight: receipt의 code revision `merge-candidate-epic-21`과 tree identity `tree-attachment-export-landed`가 현재 code tree와 일치하므로 재사용 가능하다. receipt와 별개로 아래 affected capability/entrypoint를 현재 코드와 Root에 재대조했다.
- affected capability/entrypoint: attachment export / `src/export/entrypoint.py`
- current code observation: CLI→entrypoint→ExportService wiring과 integration test가 존재한다.
- current Root observation: attachment export와 CLI registration은 landed이고 코드/evidence와 일치한다.
- proposed change: Scheduler→export entrypoint edge 추가. owner, storage policy, public boundary, ADR-0021은 유지한다.
