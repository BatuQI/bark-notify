import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { provision } from '../scripts/install.mjs';

function git(dir, ...args) {
  return execFileSync('git', ['-C', dir, ...args], { encoding: 'utf8', windowsHide: true });
}
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bark-install-test-'));
  t.after(() => {
    assert.equal(path.dirname(dir), fs.realpathSync(os.tmpdir()));
    assert.ok(path.basename(dir).startsWith('bark-install-test-'));
    fs.rmSync(dir, { recursive: true, force: true });
  });
  const repo = path.join(dir, 'source');
  fs.mkdirSync(repo);
  git(repo, 'init', '-b', 'main');
  git(repo, 'config', 'user.name', 'Test');
  git(repo, 'config', 'user.email', 'test@example.test');
  fs.mkdirSync(path.join(repo, 'scripts'));
  fs.writeFileSync(path.join(repo, 'scripts', 'install.py'), '# test fixture\n');
  fs.writeFileSync(path.join(repo, '.gitignore'), 'config.json\nconfig.local.json\n.env\n.env.*\n');
  git(repo, 'add', '.');
  git(repo, 'commit', '-m', 'initial');
  return { dir, repo, home: path.join(dir, 'codex') };
}

test('manual update preserves local settings and rules, refuses dirty code', t => {
  const { repo, home } = fixture(t);
  const target = provision(home, false, repo);
  const config = '{"device_key":"fake-key","ttl":600}\r\n';
  const rule = 'user-defined rule\n';
  fs.writeFileSync(path.join(target, 'config.json'), config);
  fs.writeFileSync(path.join(home, 'AGENTS.md'), rule);
  fs.writeFileSync(path.join(repo, 'release.txt'), 'new version');
  git(repo, 'add', '.'); git(repo, 'commit', '-m', 'update');
  provision(home, false, repo);
  assert.equal(fs.existsSync(path.join(target, 'release.txt')), false);
  provision(home, true, repo);
  assert.equal(fs.readFileSync(path.join(target, 'release.txt'), 'utf8'), 'new version');
  assert.equal(fs.readFileSync(path.join(target, 'config.json'), 'utf8'), config);
  assert.equal(fs.readFileSync(path.join(home, 'AGENTS.md'), 'utf8'), rule);
  fs.writeFileSync(path.join(target, 'release.txt'), 'user changes');
  assert.throws(() => provision(home, true, repo), /本地代码改动/);
  assert.equal(fs.readFileSync(path.join(target, 'release.txt'), 'utf8'), 'user changes');
});

test('ZIP migration backs up old files and retains local settings', t => {
  const { repo, home } = fixture(t);
  const old = path.join(home, 'skills', 'bark-notify');
  fs.mkdirSync(old, { recursive: true });
  fs.writeFileSync(path.join(old, 'config.json'), '{"ttl":600}\r\n');
  fs.writeFileSync(path.join(old, '.env'), 'local=value\n');
  fs.writeFileSync(path.join(old, 'old.txt'), 'keep in backup');
  const target = provision(home, false, repo);
  assert.equal(fs.readFileSync(path.join(target, 'config.json'), 'utf8'), '{"ttl":600}\r\n');
  assert.equal(fs.readFileSync(path.join(target, '.env'), 'utf8'), 'local=value\n');
  const backupRoot = path.join(home, 'bark-notify-backups');
  const backup = fs.readdirSync(backupRoot)[0];
  assert.equal(fs.readFileSync(path.join(backupRoot, backup, 'bark-notify', 'old.txt'), 'utf8'), 'keep in backup');
});
