#!/usr/bin/env node
/**
 * dcNess 메타 LLM telemetry 분석기
 *
 * [이슈 #284 폐기 진행] heuristic-calls.jsonl 신규 기록 0 — 누적 baseline 만 보존.
 * 신규 prose-only routing telemetry 는 .metrics/routing-decisions.jsonl
 * (`harness/routing_telemetry.py` — 이슈 #281).
 *
 * 입력 파일 (기본 `.metrics/`):
 *   - heuristic-calls.jsonl   : 옛 enum 추출 (interpret_signal) outcome (폐기 — 과거 누적 only, 신규 기록 소스 없음)
 *   - meta-llm-calls.jsonl    : haiku interpreter 가 실 호출한 케이스 (input/output_tokens, cost_usd)
 *
 * 출력: 콘솔 표 + (옵션) JSON 요약.
 *
 * 사용:
 *   node scripts/analyze_metrics.mjs                    # 기본 .metrics/
 *   node scripts/analyze_metrics.mjs --dir custom/dir   # 커스텀 디렉토리
 *   node scripts/analyze_metrics.mjs --json             # JSON 출력
 *
 * 측정 항목 (proposal R1 / R8 / §5 Phase 4 fitness):
 *   - 휴리스틱 hit rate (heuristic_hit / total)
 *   - LLM fallback rate
 *   - ambiguous (UNKNOWN) rate
 *   - 누적 비용 + 평균 비용/호출
 *   - 모델별 호출 수
 *   - allowed enum 별 outcome 분포
 *   - cost projection (cycle 당 65 호출 가정)
 */
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const args = process.argv.slice(2);
let metricsDir = '.metrics';
let jsonOutput = false;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--dir') metricsDir = args[++i];
  else if (args[i] === '--json') jsonOutput = true;
  else if (args[i] === '--help' || args[i] === '-h') {
    console.log('사용: node scripts/analyze_metrics.mjs [--dir <path>] [--json]');
    process.exit(0);
  }
}

function readJsonl(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf-8')
    .split('\n')
    .filter(l => l.trim())
    .map(l => {
      try { return JSON.parse(l); }
      catch { return null; }
    })
    .filter(Boolean);
}

const heuristicEvents = readJsonl(resolve(metricsDir, 'heuristic-calls.jsonl'));
const llmEvents = readJsonl(resolve(metricsDir, 'meta-llm-calls.jsonl'));

if (heuristicEvents.length === 0 && llmEvents.length === 0) {
  console.log(`[analyze] ${metricsDir}/ 안에 telemetry 파일 없음 — 누적 데이터 부재.`);
  console.log('         (옛 enum 추출 telemetry 는 폐기됨 — 과거 누적 데이터만 분석 가능.)');
  process.exit(0);
}

// === heuristic outcome 분포 ===
const outcomeCount = new Map();
for (const e of heuristicEvents) {
  const k = e.outcome || 'unknown';
  outcomeCount.set(k, (outcomeCount.get(k) || 0) + 1);
}

const total = heuristicEvents.length;
const heuristicHit = outcomeCount.get('heuristic_hit') || 0;
const llmHit = outcomeCount.get('llm_fallback_hit') || 0;
const llmUnknown = outcomeCount.get('llm_fallback_unknown') || 0;
const heuristicAmbiguousNoFallback = outcomeCount.get('heuristic_ambiguous_no_fallback') || 0;
const heuristicNotFound = outcomeCount.get('heuristic_not_found') || 0;
const heuristicEmpty = outcomeCount.get('heuristic_empty') || 0;

const heuristicHitRate = total > 0 ? heuristicHit / total : 0;
const llmFallbackRate = total > 0 ? (llmHit + llmUnknown) / total : 0;
const ambiguousRate = total > 0 ? (llmUnknown + heuristicAmbiguousNoFallback) / total : 0;

// === LLM 비용 ===
let totalCost = 0;
let totalInputTokens = 0;
let totalOutputTokens = 0;
const modelCount = new Map();
for (const e of llmEvents) {
  totalCost += e.cost_usd || 0;
  totalInputTokens += e.input_tokens || 0;
  totalOutputTokens += e.output_tokens || 0;
  const m = e.model || 'unknown';
  modelCount.set(m, (modelCount.get(m) || 0) + 1);
}

const avgCostPerLlmCall = llmEvents.length > 0 ? totalCost / llmEvents.length : 0;
const avgCostPerInterpret = total > 0 ? totalCost / total : 0;

// === allowed enum set 별 분포 ===
const enumOutcomes = new Map();  // key = allowed.join('|') → { total, hit, fallback, unknown }
for (const e of heuristicEvents) {
  const k = (e.allowed || []).join('|');
  if (!enumOutcomes.has(k)) {
    enumOutcomes.set(k, { total: 0, hit: 0, fallback: 0, unknown: 0 });
  }
  const bucket = enumOutcomes.get(k);
  bucket.total++;
  if (e.outcome === 'heuristic_hit') bucket.hit++;
  else if (e.outcome === 'llm_fallback_hit') bucket.fallback++;
  else if (e.outcome === 'llm_fallback_unknown' || e.outcome === 'heuristic_ambiguous_no_fallback') bucket.unknown++;
}

// === ambiguous 카탈로그 (proposal R1) ===
const ambiguousSamples = heuristicEvents
  .filter(e => e.outcome === 'llm_fallback_unknown' || e.outcome === 'heuristic_ambiguous_no_fallback')
  .slice(-5)
  .map(e => ({
    ts: e.ts,
    allowed: e.allowed,
    detail: (e.detail || e.heuristic_detail || '').substring(0, 100),
  }));

const summary = {
  total_interpret_calls: total,
  heuristic_hit_rate: heuristicHitRate,
  llm_fallback_rate: llmFallbackRate,
  ambiguous_rate: ambiguousRate,
  llm_calls: llmEvents.length,
  total_cost_usd: round(totalCost, 6),
  avg_cost_per_llm_call_usd: round(avgCostPerLlmCall, 6),
  avg_cost_per_interpret_usd: round(avgCostPerInterpret, 6),
  total_input_tokens: totalInputTokens,
  total_output_tokens: totalOutputTokens,
  outcomes: Object.fromEntries(outcomeCount),
  models: Object.fromEntries(modelCount),
  enum_distribution: Object.fromEntries(
    [...enumOutcomes.entries()].map(([k, v]) => [k, v])
  ),
  ambiguous_samples: ambiguousSamples,
  cost_projection: {
    per_cycle_65_calls_usd: round(avgCostPerInterpret * 65, 4),
    per_100_cycles_usd: round(avgCostPerInterpret * 65 * 100, 2),
  },
};

function round(n, places) {
  return Math.round(n * 10 ** places) / 10 ** places;
}

if (jsonOutput) {
  console.log(JSON.stringify(summary, null, 2));
  process.exit(0);
}

// === 사람용 표 출력 ===
console.log('==========================================');
console.log('  dcNess interpret 메트릭 리포트');
console.log('==========================================');
console.log(`  데이터 디렉토리: ${resolve(metricsDir)}`);
console.log(`  옛 enum 추출 호출 (과거 누적): ${total}`);
console.log(`  haiku 실 호출:                  ${llmEvents.length}`);
console.log('');
console.log('  Outcome 분포:');
for (const [k, v] of [...outcomeCount.entries()].sort((a, b) => b[1] - a[1])) {
  const pct = total > 0 ? ((v / total) * 100).toFixed(1) : '0.0';
  console.log(`    ${k.padEnd(40)} ${String(v).padStart(5)} (${pct}%)`);
}
console.log('');
console.log('  핵심 비율:');
console.log(`    휴리스틱 hit rate         ${(heuristicHitRate * 100).toFixed(1)}%`);
console.log(`    LLM fallback rate         ${(llmFallbackRate * 100).toFixed(1)}%`);
console.log(`    ambiguous (모호 propagate) ${(ambiguousRate * 100).toFixed(1)}%`);
console.log('');
console.log('  비용 (haiku 4.5):');
console.log(`    누적              $${totalCost.toFixed(6)}`);
console.log(`    평균/LLM 호출     $${avgCostPerLlmCall.toFixed(6)}`);
console.log(`    평균/interpret    $${avgCostPerInterpret.toFixed(6)}`);
console.log(`    cycle 당 (65호출) $${summary.cost_projection.per_cycle_65_calls_usd}`);
console.log(`    100 cycle         $${summary.cost_projection.per_100_cycles_usd}`);
console.log('');
console.log('  모델별 호출:');
for (const [m, c] of modelCount) {
  console.log(`    ${m.padEnd(40)} ${c}`);
}
console.log('');
if (enumOutcomes.size > 0) {
  console.log('  allowed enum 별 분포:');
  for (const [k, v] of enumOutcomes) {
    const hitPct = v.total > 0 ? ((v.hit / v.total) * 100).toFixed(0) : '0';
    console.log(`    [${k}]: total=${v.total}, hit=${v.hit} (${hitPct}%), fallback=${v.fallback}, unknown=${v.unknown}`);
  }
  console.log('');
}
if (ambiguousSamples.length > 0) {
  console.log('  최근 ambiguous 샘플 (proposal R1 카탈로그):');
  for (const s of ambiguousSamples) {
    console.log(`    ${s.ts} allowed=[${s.allowed.join(',')}] detail="${s.detail}"`);
  }
  console.log('');
}
console.log('  목표 (proposal §5 Phase 4):');
console.log(`    cycle 당 메타 LLM 비용 < $0.10  : ${summary.cost_projection.per_cycle_65_calls_usd < 0.10 ? '✅ PASS' : '⚠️  WATCH'}`);
console.log(`    ambiguous cycle 당 5건 미만     : ${summary.ambiguous_rate * 65 < 5 ? '✅ PASS' : '⚠️  WATCH'}`);
console.log('==========================================');
