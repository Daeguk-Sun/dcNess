# Baseline trial evidence

- execution: `2026-07-12`, isolated `/tmp` fixture copy, read-only sandbox
- provider/model: `openai-codex` / `gpt-5.6-sol`, reasoning effort `medium`
- frozen task SHA-256: `f8ef929c35dec53fde0e753908e7bc44e1dcadc9101f01a366ec53567e11dd70`
- prompt: `evals/lean-ablation/baseline-prompt.md` (`683` bytes)
- condition: lesson sentence plus `hits/last/evidence` metadata
- command executions: `2`, unique commands: `2`, identical command repeats: `0`
- wall-clock: `15.36s`
- token usage: input `38,874` (cached `24,064`), output `355`, reasoning output `9`
- cost: `측정 불가` (ChatGPT-account Codex execution exposed token counts but no per-trial billed cost)
- product AC: `2/2`; MUST-FIX `0`; regression `0`; human intervention `0`

Final response:

```json
{"entrypoint":"src/runtime.py::dispatch","owner":"src/runtime.py","stale_path":"legacy/router.py","reason":"registry.json은 route_message를 src/runtime.py::dispatch로 등록하며, 해당 파일에 실제 dispatch 구현이 있습니다. legacy/router.py의 route_message는 stale implementation으로 명시되어 있고 RuntimeError를 발생시킵니다."}
```
