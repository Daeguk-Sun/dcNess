# 플러그인 릴리즈 절차

## 1. 버전 파일 위치

두 파일을 항상 같은 버전으로 동시에 올린다.

| 파일 | 필드 |
|---|---|
| `.claude-plugin/plugin.json` | `"version"` |
| `.claude-plugin/marketplace.json` | `"metadata.version"` |

## 2. marketplace source와 artifact 계약

`plugins[].source` 는 공식 Claude Code marketplace의 GitHub source 계약으로 `release`
브랜치를 직접 소비한다.

```json
"source": {
  "source": "github",
  "repo": "Daeguk-Sun/dcNess",
  "ref": "release"
}
```

과거 0.2.2 당시 GitHub source update가 `destination is empty after copy`로 실패해 `./`로
되돌린 적이 있다. 현행 계약은 Claude Code 2.1.170 이상에서 clean install과 이전 명시 버전에서
새 명시 버전으로의 update를 모두 격리 검증한 뒤 사용한다. 같은 버전끼리의 update는 cache key가
같아 skip되므로 성공 증거로 세지 않는다. 공식 source·version 계약은
[Claude Code marketplace 문서](https://code.claude.com/docs/en/plugin-marketplaces#plugin-sources)를
따른다.

release artifact의 단일 positive allowlist SSOT는 [`scripts/release_artifact.json`](../../scripts/release_artifact.json)이다.
[`scripts/release_artifact.py`](../../scripts/release_artifact.py)의 candidate 생성·manifest digest·smoke와
[`scripts/sync_release.sh`](../../scripts/sync_release.sh)의 immutable tag publish가 이 파일만 소비한다.
`include_paths`는 제품 콘텐츠와 runtime만 선택하고, `product_python`은 배포되는 모든 Python
파일을 공개 hook·command·skill 또는 외부 사용자용 CLI 계약과 1:1로 분류한다. 포함 디렉터리
아래에 새 Python 파일이 추가돼도 `product_python`에 제품 소비자를 명시하지 않으면 artifact
build가 fail-closed 한다. `evals`, tests, build·release, dcNess 자체 effectiveness/scorecard는
repository operations이며 제품 Python이 import할 수 없다.
marketplace install/update는 그렇게 생성된 `release` ref를 소비하며, cache 비교에서 허용하는
transport/runtime metadata는 GitHub source update용 `.git`, 활성 사용 표식 `.in_use`, Python
실행이 생성하는 `**/__pycache__/*.pyc`뿐이다. bytecode 외 파일은 `__pycache__` 안에서도 허용하지
않는다. payload footprint는 이 metadata를 제외해 candidate와 비교하고, 실제 cache disk
footprint를 보고할 때는 metadata 크기를 별도로 병기한다.

공개 version은 `v{version}` tag, tag가 가리키는 tested source SHA, `snapshot`의
`manifest_sha256`과 1:1로 대응한다. `release` artifact commit의 parent가 그 source SHA이므로 별도
registry나 provenance 저장소 없이 관계를 확인할 수 있다. 같은 version의 기존 release와 candidate의
source SHA 또는 digest가 다르면 release branch를 checkout하거나 push하기 전에 실패한다. 이미 배포한
version의 tag를 이동·재사용하지 않으며 `sync_release.sh`도 tag ref를 만들거나 수정하지 않는다.

`release`는 사람이 작업하는 외부 프로젝트 브랜치 예외가 아니다. dcNess self의
`sync_release.sh`가 공식 저장소 원격(`Daeguk-Sun/dcNess`, 이전 redirect `alruminum/dcNess`)에
push할 때만 pre-push naming gate에서 기계 생성 배포 ref로 인정한다. workflow는 `main` push가 아니라
새 `vMAJOR.MINOR.PATCH` tag에서만 실행하며, exact tag source의 전체 unit suite를 통과한 뒤 publish한다.
positive allowlist build, 제품 Python inventory, version/tag/source/digest 정합, clean install/update smoke 중
하나라도 실패하면 release ref는 이전 상태로 보존된다.

```sh
# 현재 ref의 비파괴 candidate + runtime smoke + footprint/context 분리 측정
python3 scripts/release_artifact.py smoke --repo-root . --ref HEAD

# publish 경계에서는 sync가 직전 release artifact를 --previous-root로 넘겨
# clean install과 직전 version update의 source SHA / bundle digest 정합까지 검사

# 같은 revision의 저장소 Python과 release Python을 분리 측정
python3 scripts/release_artifact.py measure --repo-root . --ref HEAD

# 생성된 artifact의 repository-operations 역방향 의존 금지 확인
python3 scripts/release_artifact.py check-dependencies --root <artifact-root>

# candidate/release/cache를 같은 명령으로 측정·대조
python3 scripts/release_artifact.py snapshot --root <artifact-root>
python3 scripts/release_artifact.py compare --expected <candidate-root> --actual <cache-root>
```

baseline clean-install manifest는
[`marketplace-artifact-baseline.json`](marketplace-artifact-baseline.json)에 저장한다. 릴리즈 PR에서는
태그·공개 전에 위 smoke를 통과시킨다. FAIL이면 릴리즈를 중단하고, 현재 PR 범위에서 근본원인을
고칠 수 없을 때만 후속 이슈로 분리한다. 실제 marketplace clean install/update는 선택적 LLM
실사가 아니라 source/cache 경계를 검증하는 릴리즈 필수 실사다.

## 3. 릴리즈 순서

릴리즈 전 자기개선 점검은 [`self-improvement-loop.md`](self-improvement-loop.md)의
Sense→Diagnose→Decide→Act→Verify 루프를 따른다. 메인 agent가 내부
`scripts/release_preflight.py`를 한 번 실행해 아래 evidence 축을 순서대로 수집하고 릴리즈
가능 여부와 각 로그 경로를 보고한다. 사용자는 evidence 불일치나 새로운 사람 판정이 남은
경우에만 개입하며 Python 명령·fixture·JSON·hash를 직접 작성하거나 해석하지 않는다.

```sh
python3.11 scripts/release_preflight.py
```

이 명령은 guard efficacy, 핵심 행동 eval, 검증된 golden 기준 judge calibration, 과거 관측
제품 outcome snapshot, 실제 Agent 작업 효율 record, 최근 하네스 경량화 결정, 공개 evidence 생성·검사,
release bundle 소비 smoke를 독립 축으로 실행한다. bundle 소비 smoke와 2026-08 실측은 이
도구가 재구현하지 않고 기존 산출물·검증기를 조합한다.

기본 핵심 행동 eval은 manifest의 두 case를 각 1회 실행한다. 최초 MISS는 release FAIL로
고정되며 후속 PASS로 되돌리지 않는다. 원인 분류가 필요할 때 `--diagnose-core-misses`를 사용하면
실패 case만 case당 최대 2회, 초기 실행을 포함한 자동 총 4 trial 안에서 추가 실행하고 모든
report·judge trace를 보존한다. 4회를 넘는 표본은 사용자 승인 아래 수동 진단으로만 수집하며
이미 실패한 release 판정을 바꾸지 않는다.

`product_outcome_snapshot` 축의 `SNAPSHOT COLLECTED`는 기존 scorecard command가 종료코드 0으로
raw historical ratio·`측정 불가`·한계를 수집했다는 의미다. 현재 revision의 제품 성공률이나
제품 PASS 판정이 아니다.

하네스 실험의 월 trial ledger는 checkout 내부가 아니라 operator-wide
`~/.claude/plugins/data/dcness-dcness/harness-experiments/trial-ledger.jsonl`를 사용하므로
worktree·checkout을 나눠도 상한이 분리되지 않는다. `--ledger`는 테스트와 저장 trace
재구축 같은 명시적 운영 용도로만 덮어쓴다.

- Sense: preflight가 guard와 핵심 행동 eval을 실행하고 산출물을 `.metrics/release-preflight/` 아래에 남긴다.
- Diagnose: 전용 도구로 활성 프로젝트의 가드 발화 이력과 재발·낭비 신호([#876](https://github.com/alruminum/dcNess/issues/876)), dcNess self eval 포화 후보를 함께 본다. 새 CI 게이트가 아니라 릴리즈 전 사람이 읽는 점검이다.

  - 가드 발화 텔레메트리([#875](https://github.com/alruminum/dcNess/issues/875))가 있으면 통합 후보 표의 `guard:*` 후보를 검토한다.
  - 텔레메트리가 아직 없거나 관측 기간이 부족하면 리포트의 `관측 이력 없음(미배포 또는 무발화)` 프로젝트를 확인하고, 최근 릴리즈 이후 CI 실패, 로컬 hook 차단, PR 수정 이력을 수동 확인한다.
  - 이미 판단한 후보는 `record-decision` 으로 `docs/internal/loop-decisions.jsonl` 에 남긴다. 다음 리포트에서 `fixed`/`rejected` 는 `--hide-decided` 로 숨길 수 있고, `hold` 는 계속 표시된다.
  - 장기 무발화 guard는 바로 제거하지 않고 **소멸 후보**로만 기록한다. 실제 제거는 별도 issue/PR에서 Decide→Act→Verify를 탄다.
- Decide: 추가 전 제거 검토를 먼저 한다. 소멸 후보나 follow-up이 있으면 릴리즈 노트 `Unreleased`의 자기개선 점검 기록에 적고, 후보가 없으면 `소멸 후보 없음`이라고 적는다. 추적이 길어질 항목은 별도 GitHub issue로 분리한다.
- Verify: [`evals/core-incident-subset.json`](../../evals/core-incident-subset.json)의 핵심 행동 eval은 기본 각 1회에서 모두 통과해야 한다. 최초 MISS가 있으면 release FAIL을 유지한 채 필요한 경우에만 bounded 추가 진단으로 원인을 분류한다. judge 판정이 의심스러우면 저장된 `run-<N>-report.md`와 `run-<N>-judge.md`를 사람 golden 보정 입력으로 남기고, report digest·golden/subset version이 맞는지 확인한다.

```sh
# 1. version bump 브랜치 생성 — 브랜치명 버전은 . 대신 _ (0.25.0 → 0_25_0).
git checkout -b docs/release_0_25_0_{설명} main

# 2. 두 manifest의 version을 같은 새 값으로 올리기
#    .claude-plugin/plugin.json     "version" 필드
#    .claude-plugin/marketplace.json "metadata.version" 필드
node scripts/check_plugin_manifest.mjs

# 3. commit → PR → 전체 required CI PASS → regular merge
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "[docs] release {버전} — {설명}"
git push -u origin docs/release_0_25_0_{설명}
gh pr create --title "[docs] release {버전} — {설명}" ...

# 4. merge된 exact source에서 full preflight PASS 확인
git checkout main
git pull --ff-only origin main
python3.11 scripts/release_preflight.py

# 5. 새 immutable tag 생성·push — 기존 tag 재사용/이동 및 force push 금지
VERSION=$(python3 -c 'import json; print(json.load(open(".claude-plugin/plugin.json"))["version"])')
TAG="v${VERSION}"
SOURCE_SHA=$(git rev-parse HEAD)
git tag "$TAG" "$SOURCE_SHA"
git push origin "refs/tags/$TAG"

# 6. exact tag unit suite → clean install/update smoke → release publish workflow 확인
RUN_ID=$(gh run list --workflow=release-sync.yml --commit "$SOURCE_SHA" --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status
# workflow log의 verify-release JSON에서 아래 네 값이 일치해야 한다.
# source_sha == clean_install.source_sha == previous_version_update.source_sha
# bundle_digest == clean_install.bundle_digest == previous_version_update.bundle_digest

# 7. 사용자 업데이트 가이드 출력
echo "---"
echo "v{버전} 업데이트 가이드"
echo ""
echo "  claude plugin update dcness@dcness"
echo ""
echo "문제 발생 시:"
echo "  claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness"
echo "---"
```

> **완료 기준은 4단 정합**: `main` manifest version · immutable `v{version}` tag · release commit
> parent의 tested source SHA · release bundle digest가 1:1이어야 한다. workflow의 clean install과 직전
> version update가 같은 source SHA와 digest를 보고해야 사용자에게 도달한 것으로 본다.

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
