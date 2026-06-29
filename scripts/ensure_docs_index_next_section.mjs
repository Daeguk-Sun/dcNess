#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const SECTION_TITLE = '## 진행 상태 · 다음 작업';
const SECTION_BODY = [
  SECTION_TITLE,
  '',
  '- 진행 상태 진본: GitHub Project 보드의 Status(Todo / In progress / Done)',
  '- 작업 단위: GitHub epic/story issue 와 PR',
  '- 콜드스타트 다음 작업 확인: `/next`',
].join('\n');

const root = process.argv[2] ? path.resolve(process.argv[2]) : process.cwd();
const indexPath = path.join(root, 'docs', 'index.md');

if (!fs.existsSync(indexPath)) {
  console.log('[dcness] docs/index.md 없음 - 진행 상태 섹션 추가 skip');
  process.exit(0);
}

const text = fs.readFileSync(indexPath, 'utf8');
const hasSection = new RegExp(`^${SECTION_TITLE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`, 'm').test(text);

if (hasSection) {
  console.log('[dcness] docs/index.md 진행 상태 섹션 이미 존재 - skip');
  process.exit(0);
}

const separator = text.endsWith('\n') ? '\n' : '\n\n';
fs.appendFileSync(indexPath, `${separator}${SECTION_BODY}\n`);
console.log('[dcness] docs/index.md 진행 상태 섹션 추가');
