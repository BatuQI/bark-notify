#!/usr/bin/env python3
"""Install this skill and optionally enable the global completion rule."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys

SKILL_DIR = Path(__file__).resolve().parent.parent
START = "<!-- bark-notify:begin -->"
END = "<!-- bark-notify:end -->"


def enable_default(codex_dir, skill_dir):
    codex_dir.mkdir(parents=True, exist_ok=True)
    override = codex_dir / "AGENTS.override.md"
    agents = override if override.is_file() and override.read_bytes().decode("utf-8-sig").strip() else codex_dir / "AGENTS.md"
    original = agents.read_bytes() if agents.exists() else b""
    old = original.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in old else "\n"
    rule = "\n".join([
        START,
        "## Bark 任务完成通知（默认要求）",
        "- 每次开始用户任务时读取并遵循 `$bark-notify`，保存本次用户原文；当前任务及验证完成后、最终答复前发送一次通知。",
        "- 本人已授权将本次任务的用户消息原文（含执行中补充）和完整最终回复发送至该 Skill 配置的 Bark 接收端，不必每次确认。",
        "- title 使用当前设备名称，subtitle 使用工作区名称，body 分为“你的请求”和“任务回复”两段；不使用 Markdown，只发送一条。",
        "- 输入 JSON 保存完整请求和最终回复；通知端自动隐藏本地链接地址、缩短独立本地路径并移除内部展示指令，保留明确的 http/https 网页地址，回复转为可读普通文字。",
        "- 原始换行保留，不额外添加正文末尾换行。发送成功后在聊天中逐字输出 JSON 内的原始完整回复，不追加通知状态；聊天原始链接不受通知显示清理影响。",
        "- 只读任务也须发送完成通知，通知临时文件放在系统临时目录，不修改项目文件。",
        "- create_thread 创建的独立聊天照常发送，即使启动消息带 codex_delegation 或 source_thread_id；仅 collaboration.spawn_agent 等会话内子代理不单独发送。",
        "- 等待用户、审批、任务失败或取消时不发送。用户要求本次不通知时跳过。",
        "- 通知失败或结果未知时不自动重试，简短说明，不影响主任务结果。",
        "- 若技能列表未显示该 Skill，直接读取以下本机安装文件并遵循其中步骤：",
        "  `%s`" % (skill_dir / "SKILL.md").as_posix(),
        END,
    ]).replace("\n", newline)
    if START in old or END in old:
        if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
            raise ValueError("Existing Bark instruction markers are malformed; no instructions changed.")
        new = old[:old.index(START)] + rule + old[old.index(END) + len(END):]
    else:
        separator = "" if not old else (newline if old.endswith(newline) else newline * 2)
        new = old + separator + rule + newline
    encoded = (b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b"") + new.encode("utf-8")
    if encoded != original:
        if agents.exists():
            backup = agents.with_name(agents.name + ".bark-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
            shutil.copy2(agents, backup)
        agents.write_bytes(encoded)
    return agents


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    parser.add_argument("--skill-dir", type=Path, help="Optional exact installation folder")
    parser.add_argument("--enable-default", action="store_true", help="Add the completion rule to the active global AGENTS file")
    args = parser.parse_args(argv)
    codex_dir = args.codex_home.expanduser().resolve()
    target = (args.skill_dir or codex_dir / "skills" / "bark-notify").expanduser().resolve()
    try:
        if target != SKILL_DIR:
            if target.exists():
                raise ValueError("Target already exists; existing skill was not overwritten: %s" % target)
            shutil.copytree(SKILL_DIR, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print("Skill installed: %s" % target)
        if args.enable_default:
            print("Default enabled: %s" % enable_default(codex_dir, target))
        print("Restart Codex or open a new chat to load the instructions.")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print("Installation failed: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
