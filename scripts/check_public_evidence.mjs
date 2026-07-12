#!/usr/bin/env node

/**
 * Verify that public evidence numbers match the current checkout.
 *
 * By default this runs the full unittest suite and deterministic guard eval. Fixture
 * output flags exist so the checker itself can be tested without recursively running
 * the repository suite.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';


function fail(message) {
  process.stderr.write(`[public-evidence] FAIL — ${message}\n`);
  process.exitCode = 1;
}


function parseArgs(argv) {
  const options = { root: process.cwd(), python: process.env.PYTHON_BIN || 'python3.11' };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (!['--root', '--python', '--test-output', '--guard-output'].includes(flag)) {
      throw new Error(`unknown argument: ${flag}`);
    }
    const value = argv[index + 1];
    if (!value) {
      throw new Error(`missing value for ${flag}`);
    }
    options[flag.slice(2).replace('-', '_')] = value;
    index += 1;
  }
  if (Boolean(options.test_output) !== Boolean(options.guard_output)) {
    throw new Error('--test-output and --guard-output must be supplied together');
  }
  options.root = resolve(options.root);
  return options;
}


function readJson(path, label) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch (error) {
    throw new Error(`${label} is unreadable JSON: ${error.message}`);
  }
}


function snapshotFrom(path, label) {
  const text = readFileSync(path, 'utf8');
  const matches = [...text.matchAll(/<!-- public-evidence-snapshot (\{[^\n]+\}) -->/g)];
  if (matches.length !== 1) {
    throw new Error(`${label} must contain exactly one public-evidence-snapshot marker`);
  }
  try {
    return JSON.parse(matches[0][1]);
  } catch (error) {
    throw new Error(`${label} public-evidence-snapshot is invalid JSON: ${error.message}`);
  }
}


function run(command, args, root, label) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    input: '',
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) {
    throw new Error(`${label} could not start: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const detail = `${result.stdout || ''}${result.stderr || ''}`.trim();
    throw new Error(`${label} failed with exit ${result.status}${detail ? `: ${detail}` : ''}`);
  }
  return `${result.stdout || ''}${result.stderr || ''}`;
}


function parseTestCount(output) {
  const matches = [...output.matchAll(/Ran (\d+) tests? in /g)];
  if (matches.length !== 1 || !/\nOK(?:\s|$)/.test(output)) {
    throw new Error('unittest output must contain one successful `Ran N tests` summary');
  }
  return Number(matches[0][1]);
}


function parseGuard(output) {
  let payload;
  try {
    payload = JSON.parse(output);
  } catch (error) {
    throw new Error(`guard output is invalid JSON: ${error.message}`);
  }
  const passed = payload?.total?.passed;
  const failed = payload?.total?.failed;
  const total = payload?.total?.total;
  if (![passed, failed, total].every(Number.isInteger) || passed + failed !== total) {
    throw new Error('guard output has an invalid total summary');
  }
  if (failed !== 0) {
    throw new Error(`guard eval reported ${failed} failed case(s)`);
  }
  return { passed, total };
}


function validateSnapshot(snapshot) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(snapshot.measured_at || '')) {
    throw new Error('snapshot measured_at must be YYYY-MM-DD');
  }
  if (!Number.isInteger(snapshot.source_project_count) || snapshot.source_project_count < 1) {
    throw new Error('snapshot source_project_count must be a positive integer');
  }
  for (const key of ['unit_tests', 'guard']) {
    const metric = snapshot[key];
    if (!metric || !Number.isInteger(metric.passed) || !Number.isInteger(metric.total)) {
      throw new Error(`snapshot ${key} must contain integer passed/total`);
    }
  }
}


function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
    const manifest = readJson(resolve(options.root, '.claude-plugin/plugin.json'), 'plugin manifest');
    const readmeSnapshot = snapshotFrom(resolve(options.root, 'README.md'), 'README.md');
    const benchmarkSnapshot = snapshotFrom(
      resolve(options.root, 'docs/plugin/benchmark.md'),
      'docs/plugin/benchmark.md',
    );
    validateSnapshot(readmeSnapshot);

    if (JSON.stringify(readmeSnapshot) !== JSON.stringify(benchmarkSnapshot)) {
      fail('README/benchmark snapshot drift');
      return;
    }
    if (manifest.version !== readmeSnapshot.plugin_version) {
      fail(`plugin version drift: manifest=${manifest.version}, docs=${readmeSnapshot.plugin_version}`);
      return;
    }

    const testOutput = options.test_output
      ? readFileSync(resolve(options.test_output), 'utf8')
      : run(
          options.python,
          ['-m', 'unittest', 'discover', '-s', 'tests', '-v'],
          options.root,
          'unittest suite',
        );
    const guardOutput = options.guard_output
      ? readFileSync(resolve(options.guard_output), 'utf8')
      : run(
          options.python,
          ['evals/guard_efficacy.py', '--json'],
          options.root,
          'guard efficacy eval',
        );
    const testCount = parseTestCount(testOutput);
    const guard = parseGuard(guardOutput);

    const documentedTests = readmeSnapshot.unit_tests;
    if (documentedTests.passed !== testCount || documentedTests.total !== testCount) {
      fail(
        `unit test drift: runtime=${testCount}/${testCount}, ` +
          `docs=${documentedTests.passed}/${documentedTests.total}`,
      );
      return;
    }
    const documentedGuard = readmeSnapshot.guard;
    if (documentedGuard.passed !== guard.passed || documentedGuard.total !== guard.total) {
      fail(
        `guard drift: runtime=${guard.passed}/${guard.total}, ` +
          `docs=${documentedGuard.passed}/${documentedGuard.total}`,
      );
      return;
    }

    process.stdout.write(
      `[public-evidence] PASS — version=${manifest.version}, ` +
        `tests=${testCount}/${testCount}, guard=${guard.passed}/${guard.total}, ` +
        `measured_at=${readmeSnapshot.measured_at}, ` +
        `source_projects=${readmeSnapshot.source_project_count}\n`,
    );
  } catch (error) {
    fail(error.message);
  }
}


main();
