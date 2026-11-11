#!/usr/bin/env python3
"""Install this skill and optionally enable the global completion rule."""
import argparse
from datetime import datetime
import getpass
import json
import os
from pathlib import Path
import shutil
import sys
import urllib.parse

SKILL_DIR = Path(__file__).resolve().parent.parent
START = "<!-- bark-notify:begin -->"
END = "<!-- bark-notify:end -->"


def enable_default(codex_dir, skill_dir, custom_rule=None):
    codex_dir.mkdir(parents=True, exist_ok=True)
    override = codex_dir / "AGENTS.override.md"
    agents = override if override.is_file() and override.read_bytes().decode("utf-8-sig").strip() else codex_dir / "AGENTS.md"
    original = agents.read_bytes() if agents.exists() else b""
    old = original.decode("utf-8-sig")
    if START in old or END in old:
        if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
            raise ValueError("Existing Bark instruction markers are malformed; no instructions changed.")
        # The local rule belongs to the user, even if an older installer created it.
        return agents
    newline = "\r\n" if "\r\n" in old else "\n"
    rule = "\n".join([
        START,
        "## Bark 任务结束通知（用户配置）",
        custom_rule or "- 每个用户任务结束时发送一次通知，包括成功、失败、取消或被拦截的结果；独立聊天和只读任务也包含在内。",
        "- 在上述用户选择的范围内，任务开始时读取并遵循 `$bark-notify`，保存本次用户原文；任务结束后、最终答复前只发送一次，最终回复如实说明实际结果。成功任务先完成必要验证。",
        "- 本人授权按本机 config.json 的内容选项发送用户请求及所选的任务回复到本人配置的 Bark 接收端；后续更新不改变这项选择。",
        "- 通知格式、回复选项和显示清理由本地配置决定。原始换行保留，不额外增加末尾换行；聊天中仍输出原始完整回复。",
        "- 临时 JSON 放在系统临时目录；会话内子代理不单独发送，由主代理汇总一次。",
        "- 等待输入、等待审批、仍在执行或修复中且任务尚未结束时不发送；审批或执行被拒绝且任务就此结束时，按上述用户范围发送被拦截结果。同一次结束只尝试一次，不因等待、刷新或继续输出重复发送。用户要求本次不通知时跳过。",
        "- 取消或拦截后仍能执行工具时，停止原任务操作，仅发送结果通知，不绕过限制；强制停止或进程退出导致无法执行工具时不能保证通知，不建立后台补发。",
        "- 通知失败或结果未知时不自动重试，简短说明，不影响主任务结果。",
        "- 若技能列表未显示该 Skill，直接读取以下本机安装文件并遵循其中步骤：",
        "  `%s`" % (skill_dir / "SKILL.md").as_posix(),
        END,
    ]).replace("\n", newline)
    separator = "" if not old else (newline if old.endswith(newline) else newline * 2)
    new = old + separator + rule + newline
    encoded = (b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b"") + new.encode("utf-8")
    if encoded != original:
        if agents.exists():
            backup = agents.with_name(agents.name + ".bark-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
            shutil.copy2(agents, backup)
        agents.write_bytes(encoded)
    return agents


def validate_initial_config(config):
    server = os.environ.get("BARK_SERVER", config.get("server", ""))
    key = os.environ.get("BARK_DEVICE_KEY", config.get("device_key", ""))
    if not isinstance(server, str) or not isinstance(key, str) or not key.strip():
        raise ValueError("Please configure a Bark server and device key locally.")
    parsed = urllib.parse.urlsplit(server)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Server must be an HTTPS base URL without a key, query or credentials.")
    if not isinstance(config.get("group"), str) or type(config.get("ttl")) is not int or config["ttl"] <= 0:
        raise ValueError("group must be text; ttl must be a positive number of seconds.")
    if config.get("content_format") not in ("body", "markdown"):
        raise ValueError("Choose body or markdown for content_format.")
    if any(type(config.get(name)) is not bool for name in ("include_reply", "readable_body")):
        raise ValueError("include_reply and readable_body must be true or false.")


def prompt_settings(defaults, ask_scope=True):
    def ask(label, default):
        return input("%s [%s]: " % (label, default)).strip() or str(default)

    def yes(label, default=True):
        choice = ask(label + " (y/n)", "y" if default else "n").lower()
        if choice not in ("y", "n"):
            raise ValueError("Please answer y or n; no configuration saved.")
        return choice == "y"

    print("首次安装：通知内容会发送至你配置的 Bark 服务。已有配置在更新时不会重问或覆盖。")
    config = dict(defaults)
    config["server"] = ask("Bark 服务地址（不含 key）", defaults["server"])
    config["device_key"] = ("" if os.environ.get("BARK_DEVICE_KEY") else
                            getpass.getpass("Bark device key（不回显）: ").strip())
    config["group"] = ask("消息分组", defaults["group"])
    config["ttl"] = int(ask("保留时间，单位秒；86400 = 一天", defaults["ttl"]))
    config["content_format"] = ask("正文格式 body/markdown", defaults["content_format"])
    config["include_reply"] = yes("是否附上完整任务回复", defaults["include_reply"])
    config["readable_body"] = yes("是否清理本地链接和显示标记", defaults["readable_body"])
    print("标题自动使用当前设备名，副标题使用当前工作区名。可用 BARK_DEVICE_NAME 自定义设备名。")
    mode, custom_rule = "manual", None
    if ask_scope:
        mode = ask("通知规则：manual=仅明确调用，all=每个任务结束（成功/失败/取消/被拦截），custom=自定义", "manual")
        if mode not in ("manual", "all", "custom"):
            raise ValueError("Choose manual, all or custom; no configuration saved.")
        if mode == "custom":
            custom_rule = input("请输入通知触发规则（例如：仅代码修改任务完成后通知）: ").strip()
            if not custom_rule or START in custom_rule or END in custom_rule:
                raise ValueError("Custom notification rule is empty or contains reserved markers.")
    return config, mode, custom_rule


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--skill-dir", type=Path, help="Optional exact installation folder")
    parser.add_argument("--enable-default", action="store_true", help="Add the completion rule to the active global AGENTS file")
    parser.add_argument("--config-file", type=Path, help="First installation only: import user-approved local JSON settings")
    parser.add_argument("--rule-file", type=Path, help="User-defined notification rule; existing rules are always preserved")
    args = parser.parse_args(argv)
    codex_dir = (args.codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")).expanduser().resolve()
    target = (args.skill_dir or codex_dir / "skills" / "bark-notify").expanduser().resolve()
    try:
        if target != SKILL_DIR:
            if target.exists():
                raise ValueError("Target already exists; existing skill was not overwritten: %s" % target)
            # Never distribute the source computer's settings or Git metadata.
            shutil.copytree(SKILL_DIR, target, ignore=shutil.ignore_patterns(
                ".git", "node_modules", "__pycache__", "*.pyc", "config.json",
                "config.local.json", ".env", ".env.*", "*.zip", "*.tgz"))
        config_path = target / "config.json"
        mode, custom_rule = "manual", None
        if args.rule_file:
            custom_rule = args.rule_file.read_text(encoding="utf-8-sig").strip()
            if not custom_rule or START in custom_rule or END in custom_rule:
                raise ValueError("Custom rule is empty or contains reserved markers.")
        if config_path.exists():
            print("已沿用本地 config.json；不会重新配置或改写现有通知规则。")
        else:
            defaults = json.loads((target / "config.example.json").read_text(encoding="utf-8-sig"))
            if args.config_file:
                supplied = json.loads(args.config_file.read_text(encoding="utf-8-sig"))
                if not isinstance(supplied, dict):
                    raise ValueError("Initial configuration must be a JSON object.")
                config = dict(defaults, **supplied)
            elif sys.stdin.isatty():
                config, mode, chosen_rule = prompt_settings(defaults, not (args.enable_default or args.rule_file))
                custom_rule = custom_rule or chosen_rule
            else:
                raise ValueError("First installation needs user configuration. Run interactively or pass --config-file with user-approved settings.")
            validate_initial_config(config)
            with config_path.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(config, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            if os.name != "nt":
                config_path.chmod(0o600)
        print("Skill installed: %s" % target)
        if args.enable_default or args.rule_file or mode in ("all", "custom"):
            print("Global rule enabled or existing user rule preserved: %s" % enable_default(codex_dir, target, custom_rule))
        print("No automatic update task is created. Update manually when needed.")
        print("Restart Codex or open a new chat to load the instructions.")
        return 0
    except (OSError, UnicodeError, ValueError, EOFError) as exc:
        # JSON parse errors can contain credential fragments; do not echo them.
        message = "Invalid configuration JSON." if isinstance(exc, json.JSONDecodeError) else str(exc)
        print("Installation failed: %s" % message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
