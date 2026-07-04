# 플러그인 릴리즈 절차

## 1. 버전 파일 위치

두 파일을 항상 같은 버전으로 동시에 올린다.

| 파일 | 필드 |
|---|---|
| `.claude-plugin/plugin.json` | `"version"` |
| `.claude-plugin/marketplace.json` | `"metadata.version"` |

## 2. 주의사항 — marketplace.json source 형식

`plugins[].source` 는 반드시 `"./"` 형식이어야 한다.

```json
"source": "./"   ✅
```

GitHub object 형식(`{"source": "github", "repo": "...", "ref": "release"}`)은 `claude plugin install`(신규)은 동작하지만 `claude plugin update`에서 "destination is empty after copy" 오류 발생. (0.2.3에서 수정됨)

## 3. 릴리즈 순서

릴리즈 전 자기개선 점검은 [`self-improvement-loop.md`](self-improvement-loop.md)의
Sense→Diagnose→Decide→Act→Verify 루프를 따른다. 새 CI 게이트가 아니라 사람이 도는
권고 절차다.

- Sense: `python3 evals/guard_efficacy.py`와 `EVAL_RUNS=3 EVAL_RELEASE_CHECK=1 bash evals/run.sh`를 실행한다. 행동 eval 산출물은 `.metrics/evals/` 또는 `EVAL_OUTPUT_DIR`에 남긴다.
- Diagnose: 전용 도구로 활성 프로젝트의 가드 발화 이력과 재발·낭비 신호([#876](https://github.com/alruminum/dcNess/issues/876)), dcNess self eval 포화 후보를 함께 본다. 새 CI 게이트가 아니라 릴리즈 전 사람이 읽는 점검이다.

  ```sh
  python3.11 scripts/loop_diagnose.py --idle-days 30 --saturation-days 30 --saturation-min-runs 3
  ```

  - 가드 발화 텔레메트리([#875](https://github.com/alruminum/dcNess/issues/875))가 있으면 통합 후보 표의 `guard:*` 후보를 검토한다.
  - 텔레메트리가 아직 없거나 관측 기간이 부족하면 리포트의 `관측 이력 없음(미배포 또는 무발화)` 프로젝트를 확인하고, 최근 릴리즈 이후 CI 실패, 로컬 hook 차단, PR 수정 이력을 수동 확인한다.
  - 이미 판단한 후보는 `record-decision` 으로 `docs/internal/loop-decisions.jsonl` 에 남긴다. 다음 리포트에서 `fixed`/`rejected` 는 `--hide-decided` 로 숨길 수 있고, `hold` 는 계속 표시된다.
  - 장기 무발화 guard는 바로 제거하지 않고 **소멸 후보**로만 기록한다. 실제 제거는 별도 issue/PR에서 Decide→Act→Verify를 탄다.
- Decide: 추가 전 제거 검토를 먼저 한다. 소멸 후보나 follow-up이 있으면 릴리즈 노트 `Unreleased`의 자기개선 점검 기록에 적고, 후보가 없으면 `소멸 후보 없음`이라고 적는다. 추적이 길어질 항목은 별도 GitHub issue로 분리한다.
- Verify: 핵심 행동 eval(`shorts-real-spec`, `headless-prose-quality`)은 릴리즈 체크 모드에서 N/N 통과해야 한다. judge 판정이 의심스러우면 저장된 `run-<N>-report.md`와 `run-<N>-judge.md`를 [#894](https://github.com/alruminum/dcNess/issues/894) 보정 입력으로 남긴다.

```sh
# 1. 브랜치 생성
git checkout -b docs/release_{버전}_{설명} main

# 2. 버전 올리기
#    .claude-plugin/plugin.json     "version" 필드
#    .claude-plugin/marketplace.json "metadata.version" 필드

# 3. 커밋
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "[docs] release {버전} — {설명}"

# 4. PR 생성 → CI PASS → merge
git push -u origin docs/release_{버전}_{설명}
gh pr create --title "[docs] release {버전} — {설명}" ...
gh pr merge {번호} --merge

# 5. main pull 후 태그 박기
git checkout main && git pull
git tag v{버전} && git push origin v{버전}

# 6. 사용자 업데이트 가이드 출력
echo "---"
echo "v{버전} 업데이트 가이드"
echo ""
echo "  claude plugin update dcness@dcness"
echo ""
echo "문제 발생 시:"
echo "  claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness"
echo "---"
```

## 4. 릴리즈 후 사용자 검증 방법

```sh
claude plugin marketplace update dcness
claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness
cat ~/.claude/plugins/installed_plugins.json | python3 -c \
  "import json,sys;d=json.load(sys.stdin);print(d['plugins']['dcness@dcness'][0]['version'])"
```

> `claude plugin update dcness@dcness` 는 현재 정상 동작하나, 문제 발생 시 uninstall → install 로 대체.

## 5. 릴리즈 노트 관리

[`docs/internal/release-notes.md`](release-notes.md) 에 버전별 변경 요약 기록.
