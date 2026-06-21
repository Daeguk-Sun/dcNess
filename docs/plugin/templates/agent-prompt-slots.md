# Agent Prompt 3-Slot Template

> 메인 Claude 가 action loop(`/impl` · `/impl-loop` · `/design`)에서 sub-agent 호출 prompt 를 쓸 때 사용하는 입력 템플릿이다. 출력 형식 강제가 아니라, 호출자가 prompt 에 담을 정보의 칸을 고정해 worktree 누락과 방법 처방을 줄이는 장치다.

```markdown
**대상 + 읽을 진본:** {{이번 호출이 다룰 단위 + 그 진본 경로.
agent 가 자체 read 할 SSOT 경로를 적는다.
진본(task 파일 Scope·수용기준·인터페이스 · 이슈)에 이미 있으면 prompt 에 재기입하지 않는다.
예) Lite=이슈 #NN · impl(test-engineer·engineer)=task 파일
    · code-validator·pr-reviewer=검토 대상(task 파일 + 변경 코드/diff)
    · system-architect=docs/index.md + 전역/epic SSOT
    · module-architect=Story N + docs/index.md + 전역 decisions + epic architecture·domain-model·stories(Story 섹션)
    · architecture-validator=검토 대상 산출물}}

**worktree:** {{활성 시 worktree 절대 경로.
비활성이 확실하면 생략한다.
활성 여부가 애매하면 `pwd` / `git rev-parse --show-toplevel` 로 확인한 뒤 적는다.
main repo 절대경로를 worktree 경로처럼 넘기지 않는다.}}

**이 호출 특유:** {{진본에 아직 없는 것만.
진본이 충실하면 이 칸은 비워도 된다.
예) 미기록 결정·신호(그릴미 합의 · Cross-Story Lessons · wave-plan 신호)
    · 재호출 finding relay(근본 원인 + 증상 패턴)
    · 진본 누락이라 주는 미기록 사실(해당 agent 가 진본에 기록해야 함)
금지: 정규식·구현 단계·알고리즘·테스트 assert 방식 등 agent 본업의 방법 처방.
채워도 "무엇/어느 단위" 까지만 적고, "어떻게" 는 agent 가 정한다.}}
```

## 슬롯 해석

- **슬롯 1**: 대상 단위 + 읽을 SSOT + write 경계. 같은 결정·계약·요구사항을 prompt 에 다시 복사하지 않는다.
- **슬롯 2**: worktree 활성 시 절대경로. Claude Code Task tool 에 cwd 전달 경로가 없으므로 메인이 명시한다.
- **슬롯 3**: 그 호출에만 필요한 미기록 제약·신호. 방법 처방을 막는 가드다.

진본이 충실한 호출은 슬롯 1 + 슬롯 2 + 필요한 경우 슬롯 3 한 줄로 수렴한다.
