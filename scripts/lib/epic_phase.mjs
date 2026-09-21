/**
 * Epic 의 현재 phase 와 다음 액션을 durable 산출물(파일 존재)만으로 파생하는 SSOT helper.
 *
 * 콜드스타트 세션이 auto-memory 없이도 "spec 완료 → design 차례" 같은 다음 액션을
 * dcNess 산출물만으로 확정하게 하려는 공용 판정. 같은 신호를 두 곳에서 계산하지 않도록
 * 여기 한 곳에 둔다:
 *  - scripts/aggregate_index_map.mjs — docs/index.md `## 에픽` 표의 `다음 액션` 파생 컬럼
 *  - scripts/github_project_lifecycle.mjs next-work — epic별 `/design` vs `/impl` 구분
 *
 * 설계 완료 판정 기준 (docs/plugin/deliverables-map.md full design pack):
 *   architecture.md 존재 AND impl/NN-*.md 1개 이상 존재.
 *   domain-model.md / ux-flow.md / tech-review.md 는 선택 산출물이라 판정에서 제외한다
 *   (선택 산출물 부재를 설계 미완으로 오판하지 않는다).
 *   단, ux-flow.md 존재 + full design pack 부재는 UI epic 의 stage 1 완료 신호로
 *   "`/design` (ux 완료 · system 미완)" 라벨만 세분화한다.
 *
 * 완료된 pack 의 staged revision (#1211):
 *   신규 설계에서는 pack 부재가 stage 경계를 드러내지만, *개정* 에서는 pack 이 이미
 *   완성돼 있어 stage 1 revision 을 머지한 직후에도 파일 존재만으로는 "설계 완료" 로
 *   보인다. 그래서 stage 1 절차가 REVISION_PENDING_FILE 을 남기고 stage 2 절차가
 *   지운다. 이 파일이 있으면 전파가 끝나지 않은 것이므로 impl 로 보내지 않는다.
 */
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const IMPL_TASK_RE = /^\d+-.*\.md$/;

/** stage 1 revision 이 남기고 stage 2 revision 이 지우는 전파 대기 표식 (#1211). */
export const REVISION_PENDING_FILE = 'revision-pending.md';

export function hasImplTask(epicDir) {
  const implDir = join(epicDir, 'impl');
  if (!existsSync(implDir)) return false;
  try {
    return readdirSync(implDir, { withFileTypes: true }).some(
      (entry) => entry.isFile() && IMPL_TASK_RE.test(entry.name)
    );
  } catch {
    return false;
  }
}

export function isDesignComplete(epicDir) {
  return existsSync(join(epicDir, 'architecture.md')) && hasImplTask(epicDir);
}

export function isUxStageComplete(epicDir) {
  return existsSync(join(epicDir, 'ux-flow.md'));
}

/** 완료된 pack 의 stage 1 개정이 머지됐고 system/module 전파가 남았는가 (#1211). */
export function isRevisionPropagationPending(epicDir) {
  return existsSync(join(epicDir, REVISION_PENDING_FILE));
}

/**
 * @param {string} epicDir  docs/epics/epic-NN-<slug> 절대/상대 경로
 * @returns {{ phase: 'spec'|'design'|'impl', action: '/spec'|'/design'|'/impl', label: string }}
 *   label = docs/index.md 셀·next-work 출력에 넣는 사람이 읽는 문구.
 */
export function epicPhase(epicDir) {
  if (!existsSync(join(epicDir, 'stories.md'))) {
    return { phase: 'spec', action: '/spec', label: '`/spec` (스펙 미작성)' };
  }
  if (!isDesignComplete(epicDir)) {
    if (isUxStageComplete(epicDir)) {
      return { phase: 'design', action: '/design', label: '`/design` (ux 완료 · system 미완)' };
    }
    return { phase: 'design', action: '/design', label: '`/design` (설계 미완)' };
  }
  if (isRevisionPropagationPending(epicDir)) {
    return {
      phase: 'design',
      action: '/design',
      label: '`/design` (UX 개정 머지됨 · system 전파 대기)',
    };
  }
  return { phase: 'impl', action: '/impl', label: '`/impl` (설계 완료)' };
}
