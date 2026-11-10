#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const REPOSITORY = 'https://github.com/BatuQI/bark-notify.git';

function command(program, args, options = {}) {
  const result = spawnSync(program, args, { encoding: 'utf8', windowsHide: true, ...options });
  if (result.error || result.status !== 0) {
    throw new Error(`${program} 执行失败；已有文件和配置不会被强制重置。`);
  }
  return (result.stdout || '').trim();
}

function findPython() {
  for (const candidate of [['python3'], ['python'], ['py', '-3']]) {
    const result = spawnSync(candidate[0], [...candidate.slice(1), '-c',
      'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'],
      { encoding: 'utf8', windowsHide: true, timeout: 10000 });
    if (!result.error && result.status === 0) return candidate;
  }
  throw new Error('需要 Python 3.9+。请安装 Python 后重新运行本命令。');
}

function sameRepository(actual, expected) {
  return actual.replace(/\.git$/, '').replace(/\/$/, '') === expected.replace(/\.git$/, '').replace(/\/$/, '');
}

// repoUrl is injectable for isolated tests; the CLI always uses REPOSITORY.
export function provision(codexHome, update = false, repoUrl = REPOSITORY) {
  const home = path.resolve(codexHome);
  const target = path.join(home, 'skills', 'bark-notify');
  fs.mkdirSync(home, { recursive: true });
  command('git', ['--version']);
  if (fs.existsSync(target) && fs.lstatSync(target).isSymbolicLink()) {
    throw new Error('安装目录是符号链接；请在实际工作副本中手动更新。');
  }
  if (fs.existsSync(path.join(target, '.git'))) {
    const top = command('git', ['-C', target, 'rev-parse', '--show-toplevel']);
    if (path.resolve(top) !== path.resolve(fs.realpathSync(target))) throw new Error('Git 工作副本路径不匹配。');
    const remote = command('git', ['-C', target, 'remote', 'get-url', 'origin']);
    if (!sameRepository(remote, repoUrl)) throw new Error('已有目录属于其他 Git 仓库；未修改。');
    if (update) {
      if (command('git', ['-C', target, 'branch', '--show-current']) !== 'main') {
        throw new Error('当前不在 main 分支；请先处理自己的分支。');
      }
      if (command('git', ['-C', target, 'status', '--porcelain'])) {
        throw new Error('存在本地代码改动或未跟踪文件；请先处理，配置和规则未改动。');
      }
      if (command('git', ['-C', target, 'ls-files', '--', 'config.json', 'config.local.json', '.env', '.env.*'])) {
        throw new Error('本地配置被 Git 跟踪；停止更新以保留用户设置。');
      }
      command('git', ['-C', target, 'pull', '--ff-only', 'origin', 'main'], { stdio: 'inherit' });
    } else {
      console.log('已有安装：沿用当前版本。需要手动更新时添加 --update。');
    }
    return target;
  }

  // Stage on the same volume before backing up an existing ZIP installation.
  const staging = fs.mkdtempSync(path.join(home, '.bark-install-'));
  const checkout = path.join(staging, 'bark-notify');
  command('git', ['clone', '--branch', 'main', '--single-branch', repoUrl, checkout], { stdio: 'inherit' });
  if (!fs.existsSync(path.join(checkout, 'scripts', 'install.py'))) {
    throw new Error(`仓库缺少安装脚本；未替换已有目录。临时副本：${checkout}`);
  }
  let backup;
  if (fs.existsSync(target)) {
    for (const name of fs.readdirSync(target)) {
      if (['config.json', 'config.local.json', '.env'].includes(name) || name.startsWith('.env.')) {
        const source = path.join(target, name);
        if (fs.lstatSync(source).isSymbolicLink()) throw new Error('本地配置是符号链接；请手动迁移。');
        if (fs.statSync(source).isFile()) fs.copyFileSync(source, path.join(checkout, name), fs.constants.COPYFILE_EXCL);
      }
    }
    const backupRoot = path.join(home, 'bark-notify-backups');
    fs.mkdirSync(backupRoot, { recursive: true });
    backup = fs.mkdtempSync(path.join(backupRoot, 'previous-'));
    // Both source and destination are explicit children of the selected CODEX_HOME.
    fs.renameSync(target, path.join(backup, 'bark-notify'));
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  try {
    fs.renameSync(checkout, target);
  } catch (error) {
    if (backup && !fs.existsSync(target)) fs.renameSync(path.join(backup, 'bark-notify'), target);
    throw error;
  }
  fs.rmdirSync(staging); // Empty directory only; failed clones are retained for inspection.
  if (backup) console.log(`旧版本已备份：${backup}`);
  return target;
}

export function main(args = process.argv.slice(2)) {
  if (args.includes('--help') || args.includes('-h')) {
    console.log('安装：npx --yes github:BatuQI/bark-notify\n手动更新：npx --yes github:BatuQI/bark-notify --update\n首次安装交互配置；后续保留 config.json 和用户通知规则，不创建定时任务。\n需要 Node.js 18+、Git、Python 3.9+。\n可选：--codex-home <目录> --config-file <首次配置JSON> --enable-default 或 --rule-file <自定义规则文件>');
    return 0;
  }
  let codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex');
  let update = false;
  const forwarded = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--update') update = true;
    else if (arg === '--enable-default') forwarded.push(arg);
    else if (['--codex-home', '--config-file', '--rule-file'].includes(arg)) {
      if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error(`${arg} 缺少值。`);
      const value = path.resolve(args[++i]);
      if (arg === '--codex-home') codexHome = value;
      else forwarded.push(arg, value);
    } else throw new Error(`未知参数：${arg}`);
  }
  const python = findPython();
  const target = provision(codexHome, update);
  command(python[0], [...python.slice(1), '-X', 'utf8', path.join(target, 'scripts', 'install.py'),
    '--codex-home', path.resolve(codexHome), ...forwarded], { stdio: 'inherit' });
  return 0;
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { process.exitCode = main(); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
