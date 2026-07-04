# /loop-diagnose

dcNess self 전용 Diagnose 도구를 실행한다. 이 command 는 외부 활성 프로젝트로 배포하지
않는다.

## 절차

1. dcNess repo root 에서 도구를 실행한다.

   ```sh
   python3.11 scripts/loop_diagnose.py
   ```

   필요 시 JSON 으로 확인한다.

   ```sh
   python3.11 scripts/loop_diagnose.py --json
   ```

2. stdout 리포트를 그대로 echo 한다. `/run-review` 와 같은 원칙으로 섹션 생략, 표 재배치,
   자체 요약 삽입을 하지 않는다.

3. 통합 후보 표를 보고 후보를 분류한다.
   - blocker: 릴리즈 전에 별도 issue/PR 로 Decide→Act→Verify 를 탄다.
   - release-note follow-up: `docs/internal/release-notes.md` 의 자기개선 점검 기록에 적는다.
   - 기각 또는 이미 처리: 결정 원장에 소비 표식을 남긴다.

4. 후보별 결정을 기록한다.

   ```sh
   python3.11 scripts/loop_diagnose.py record-decision \
     --key "guard:file-guard@project" \
     --decision hold \
     --ref "#NNN"
   ```

   `--decision` 은 `fixed`, `hold`, `rejected` 중 하나다. `fixed`/`rejected` 후보는 다음
   리포트에서 `--hide-decided` 로 숨길 수 있고, `hold` 는 계속 표시된다.

5. 릴리즈 점검 중이면 release notes 의 "자기개선 점검 기록" 표에 결론을 남긴다.

## 참조

- `scripts/loop_diagnose.py`
- `docs/internal/self-improvement-loop.md`
- `docs/internal/plugin-release.md`
