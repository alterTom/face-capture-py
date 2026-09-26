import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const packageDir = fileURLToPath(new URL('../../../packages/face-capture-vue3/', import.meta.url));
const exampleDir = fileURLToPath(new URL('../', import.meta.url));
const npmCli = process.env.npm_execpath;

function npm(cwd, ...args) {
  return spawnSync(process.execPath, [npmCli, ...args], {
    cwd,
    encoding: 'utf8'
  });
}

test('npm distribution builds and contains its Vue entry, SDK and styles', () => {
  const build = npm(packageDir, 'run', 'build');
  assert.equal(build.status, 0, build.stderr || build.error?.message);

  const packed = npm(packageDir, 'pack', '--dry-run', '--json', '--ignore-scripts');
  assert.equal(packed.status, 0, packed.stderr || packed.error?.message);
  const files = JSON.parse(packed.stdout)[0].files.map(file => file.path);
  assert.ok(files.includes('dist/index.js'));
  assert.ok(files.includes('dist/style.css'));
  assert.ok(files.includes('dist/index.d.ts'));
  assert.ok(files.includes('README.md'));
  assert.ok(files.every(file => !file.startsWith('node_modules/') && !file.startsWith('tests/')));

  const consumer = npm(exampleDir, 'run', 'build');
  assert.equal(consumer.status, 0, consumer.stderr || consumer.error?.message);
});
