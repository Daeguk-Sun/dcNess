# Agent Prompt 3-Slot Template

> 메인 Claude 가 action loop(`/impl` · `/impl-loop` · `/design`)에서 sub-agent 호출 prompt 를 쓸 때 사용하는 입력 템플릿이다. 출력 형식 강제가 아니라, 호출자가 prompt 에 담을 정보의 칸을 고정해 worktree 누락과 방법 처방을 줄이는 장치다.

```markdown
**대상 + 읽을 진본:** {{이번 호출이 다룰 단위 + 그 진본 경로.
agent 가 자체 read 할 SSOT 경로를 적는다.
진본(task 파일 Scope·수용기준·인터페이스 · 이슈)에 이미 있으면 prompt 에 재기입하지 않는다.
예) direct `/impl`=이슈 #NN · impl-loop(build-worker)=task 파일
    · impl-loop(build-worker) design:required=task 파일 + build-worker 읽을 진본에 `docs/design.md` 토큰 필수 포함
    · impl-validator=검토 대상(merge candidate diff + 계획 파일 유무 + target GitHub issue AC snapshot 또는 issue 없음 사유 + 테스트 증거)
    · system-architect(thin bootstrap)=docs/index.md + PRD + root architecture/conventions/decisions + stories
    · system-architect(checkpoint)=docs/index.md + 전역/epic SSOT + affected module docs + 코드 계약 표면
    · module-architect=epic-batch + docs/index.md + 전역 decisions + affected module docs + epic architecture·선택 domain-model·전체 stories + 코드 계약 표면
      + 확정 목업 존재 UI epic 이면 docs/design.md + 확정 목업 파일 + docs/design-variants/canvas.html + node-id 매핑 + 핵심 디자인 토큰
    · architecture-validator=검토 대상 산출물
      + 확정 목업 존재 UI epic 이면 docs/design.md + 확정 목업 파일 + docs/design-variants/canvas.html + node-id 매핑}}

**worktree:** {{동적 lifecycle context가 전달한다.
foreground Claude Agent는 SubagentStart hook, headless worker는 wrapper가 절대경로를 첫 prompt에 넣는다.
메인은 Bash stdout을 이 칸에 재전달하지 않고, 별도 비표준 provider에서만 동등한 직접 전달을 보장한다.
main repo 절대경로를 worktree 경로처럼 주입하지 않는다.}}

**이 호출 특유:** {{진본에 아직 없는 것만.
진본이 충실하면 이 칸은 비워도 된다.
예) 미기록 결정·신호(그릴미 합의 · Cross-Story Lessons · wave-plan 신호)
    · 재호출 finding relay(근본 원인 + 증상 패턴)
    · 진본 누락이라 주는 미기록 사실(해당 agent 가 진본에 기록해야 함)
금지: 정규식·구현 단계·알고리즘·테스트 assert 방식 등 agent 본업의 방법 처방.
채워도 "무엇/어느 단위" 까지만 적고, "어떻게" 는 agent 가 정한다.}}
```

## 슬롯 해석

- **슬롯 1**: 대상 단위 + 읽을 SSOT + write 경계. 같은 결정·계약·요구사항을 prompt 에 다시 복사하지 않는다. **외부 활성 프로젝트에서 sub-agent 의 *자기 전체 지침*(얇은 진입점이 가리키는 `docs/plugin/agents/<name>/<name>-agent.md`) 경로는 cwd 상대가 아니라 활성 plugin root 기준**이므로, 메인이 진입 때 최초 resolve한 `<PLUGIN_ROOT_ABS>/docs/plugin/agents/<name>/<name>-agent.md` literal을 슬롯 1에 적는다. shell 변수는 독립 Bash tool 호출 사이에 지속되지 않는다. `dcness-helper` self-location은 발견된 executable 내부 root 해소이며 executable 자체 발견과 구분한다. dcness self 저장소면 cwd 상대경로 그대로.
- **슬롯 2**: worktree 활성 시 lifecycle hook/wrapper가 절대경로를 직접 전달한다. main prompt에 중복 사본을 만들지 않는다.
- **슬롯 3**: 그 호출에만 필요한 미기록 제약·신호. 방법 처방을 막는 가드다.

진본이 충실한 호출은 슬롯 1 + 슬롯 2 + 필요한 경우 슬롯 3 한 줄로 수렴한다.
