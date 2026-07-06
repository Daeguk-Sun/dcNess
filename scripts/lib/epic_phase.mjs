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
 */
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const IMPL_TASK_RE = /^\d+-.*\.md$/;

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
    return { phase: 'design', action: '/design', label: '`/design` (설계 미완)' };
  }
  return { phase: 'impl', action: '/impl', label: '`/impl` (설계 완료)' };
}
