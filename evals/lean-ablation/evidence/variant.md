# Variant trial evidence

- execution: `2026-07-12`, isolated `/tmp` fixture copy, read-only sandbox
- provider/model: `openai-codex` / `gpt-5.6-sol`, reasoning effort `medium`
- frozen task SHA-256: `f8ef929c35dec53fde0e753908e7bc44e1dcadc9101f01a366ec53567e11dd70`
- prompt: `evals/lean-ablation/variant-prompt.md` (`576` bytes)
- condition: lesson sentence retained; `hits/last/evidence` metadata removed
- command executions: `2`, unique commands: `2`, identical command repeats: `0`
- wall-clock: `13.81s`
- token usage: input `40,659` (cached `26,112`), output `366`, reasoning output `13`
- cost: `측정 불가` (ChatGPT-account Codex execution exposed token counts but no per-trial billed cost)
- product AC: `2/2`; MUST-FIX `0`; regression `0`; human intervention `0`

Final response:

```json
{"entrypoint":"src/runtime.py::dispatch","owner":"src/runtime.py","stale_path":"legacy/router.py","reason":"registry.json이 route_message를 src/runtime.py::dispatch로 등록하고, 해당 함수가 실제 정상 구현입니다. legacy/router.py의 route_message는 스스로 stale 구현임을 명시하며 RuntimeError를 발생시키므로 stale 경로입니다."}
```
