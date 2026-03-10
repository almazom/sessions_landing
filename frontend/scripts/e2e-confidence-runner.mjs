import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

function getNumberEnv(name, fallback) {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const parsedValue = Number(rawValue);
  return Number.isNaN(parsedValue) ? fallback : parsedValue;
}

function getBooleanEnv(name, fallback) {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  return !['0', 'false', 'False', 'FALSE', 'no', 'No', 'NO'].includes(rawValue);
}

function commandExists(command) {
  const result = spawnSync('bash', ['-lc', `command -v ${command}`], {
    stdio: 'ignore',
    env: process.env,
  });
  return result.status === 0;
}

function timestampId() {
  return new Date().toISOString().replaceAll(':', '-').replace(/\..+/, 'Z');
}

function ensureDirectory(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function sendTextViaT2me(message, sendT2me) {
  if (!sendT2me || !commandExists('t2me')) {
    return { sent: false };
  }

  const result = spawnSync('t2me', ['send', message], {
    encoding: 'utf8',
    env: process.env,
  });

  return {
    sent: result.status === 0,
    stdout: result.stdout?.trim() || '',
    stderr: result.stderr?.trim() || '',
  };
}

function getPipelineMode() {
  const cliModeIndex = process.argv.indexOf('--mode');
  if (cliModeIndex >= 0 && process.argv[cliModeIndex + 1]) {
    return process.argv[cliModeIndex + 1];
  }

  return process.env.NEXUS_E2E_PIPELINE_MODE || 'smoke';
}

function getPublicUrl() {
  const cliArgs = process.argv.slice(2);
  for (let index = 0; index < cliArgs.length; index += 1) {
    if (cliArgs[index] === '--mode') {
      index += 1;
      continue;
    }

    if (!cliArgs[index].startsWith('--')) {
      return cliArgs[index];
    }
  }

  return '';
}

async function main() {
  const pipelineMode = getPipelineMode();
  const publicUrl = getPublicUrl();
  const minRuns = getNumberEnv('NEXUS_E2E_MIN_RUNS', 5);
  const maxRuns = getNumberEnv('NEXUS_E2E_MAX_RUNS', 6);
  const threshold = getNumberEnv('NEXUS_E2E_CONFIDENCE_THRESHOLD', 0.95);
  const sendT2me = getBooleanEnv('NEXUS_E2E_SEND_T2ME', true);

  const outputRoot = path.resolve(
    process.cwd(),
    '..',
    'tmp',
    'e2e-confidence',
    `${pipelineMode}-run-${timestampId()}`,
  );
  ensureDirectory(outputRoot);

  const attempts = [];
  let successCount = 0;

  for (let runIndex = 1; runIndex <= maxRuns; runIndex += 1) {
    console.log(`[confidence] run ${runIndex}/${maxRuns} :: mode=${pipelineMode}`);

    const args = ['scripts/e2e-smoke-pipeline.mjs', '--mode', pipelineMode];
    if (publicUrl) {
      args.push(publicUrl);
    }

    const result = spawnSync('node', args, {
      cwd: process.cwd(),
      encoding: 'utf8',
      env: process.env,
      maxBuffer: 1024 * 1024 * 8,
    });

    const runSummary = {
      run: runIndex,
      status: result.status ?? 1,
      success: result.status === 0,
      stdout: result.stdout || '',
      stderr: result.stderr || '',
    };

    attempts.push(runSummary);
    if (runSummary.success) {
      successCount += 1;
    }

    const currentRate = successCount / runIndex;
    console.log(`[confidence] success-rate=${currentRate.toFixed(3)} after ${runIndex} run(s)`);

    if (runIndex >= minRuns && currentRate >= threshold) {
      break;
    }
  }

  const confidence = successCount / attempts.length;
  const summary = {
    pipeline_mode: pipelineMode,
    min_runs: minRuns,
    max_runs: maxRuns,
    threshold,
    runs: attempts.length,
    success_count: successCount,
    confidence,
    satisfied: attempts.length >= minRuns && confidence >= threshold,
    attempts,
  };

  fs.writeFileSync(
    path.join(outputRoot, 'summary.json'),
    `${JSON.stringify(summary, null, 2)}\n`,
  );

  console.log(JSON.stringify(summary, null, 2));

  sendTextViaT2me(
    `E2E ${pipelineMode} confidence: ${(confidence * 100).toFixed(1)}% (${successCount}/${attempts.length}). Threshold ${(threshold * 100).toFixed(0)}%. ${summary.satisfied ? 'Satisfied.' : 'Not yet satisfied.'}`,
    sendT2me,
  );

  if (!summary.satisfied) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
