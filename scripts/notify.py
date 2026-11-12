#!/usr/bin/env python3
"""Send a Bark notification, optionally shortening an oversized final reply."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

SKILL_DIR = Path(__file__).resolve().parent.parent
# Conservative preflight budget, not a claim about every Bark server's limit.
LONG_REPLY_PAYLOAD_BYTES = 3500
OUTCOME_TEXT = {"success": "已完成", "failure": "任务失败",
                "cancelled": "已取消", "blocked": "任务被拦截",
                "unknown": "任务已结束"}


class NotificationError(Exception):
    pass


class PayloadTooLarge(NotificationError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def device_name():
    override = os.environ.get("BARK_DEVICE_NAME", "").strip()
    if override:
        return override
    system = platform.system()
    if system == "Windows":
        name = os.environ.get("COMPUTERNAME", "").strip()
        if name:
            return name
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["/usr/sbin/scutil", "--get", "ComputerName"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    name = socket.gethostname().strip()
    if not name:
        raise NotificationError("Cannot determine the current device name.")
    return name


def load_config(path):
    try:
        config = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise NotificationError("Cannot read a valid UTF-8 JSON config.") from exc
    if not isinstance(config, dict):
        raise NotificationError("Config must be a JSON object.")
    server = os.environ.get("BARK_SERVER", config.get("server", "https://api.day.app"))
    key = os.environ.get("BARK_DEVICE_KEY", config.get("device_key", ""))
    if not isinstance(server, str) or not isinstance(key, str) or not key.strip():
        raise NotificationError("Configure server and device_key before sending.")
    parsed = urllib.parse.urlsplit(server)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise NotificationError("Bark server must be an HTTPS base URL without credentials or query.")
    group = config.get("group", "example")
    ttl = config.get("ttl", 86400)
    content_format = config.get("content_format", "body")
    include_reply = config.get("include_reply", False)
    readable_body = config.get("readable_body", False)
    long_reply_fallback = config.get("long_reply_fallback", False)
    if not isinstance(group, str) or type(ttl) is not int or ttl < 0:
        raise NotificationError("group must be text; ttl must be a nonnegative integer.")
    if content_format not in ("body", "markdown"):
        raise NotificationError("content_format must be body or markdown.")
    if type(include_reply) is not bool:
        raise NotificationError("include_reply must be a boolean.")
    if type(readable_body) is not bool:
        raise NotificationError("readable_body must be a boolean.")
    if type(long_reply_fallback) is not bool:
        raise NotificationError("long_reply_fallback must be a boolean.")
    return {"server": server.rstrip("/"), "device_key": key.strip(),
            "group": group, "ttl": ttl, "content_format": content_format,
            "include_reply": include_reply, "readable_body": readable_body,
            "long_reply_fallback": long_reply_fallback}


def read_messages(path):
    """Decode message strings; JSON document whitespace is not user content."""
    try:
        document = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise NotificationError("Cannot read a valid UTF-8 messages JSON file.") from exc
    messages = document.get("messages") if isinstance(document, dict) else None
    if not isinstance(messages, list) or not messages or any(not isinstance(message, str) for message in messages):
        raise NotificationError("Messages JSON must contain a nonempty messages array of strings.")
    reply = document.get("reply")
    if reply is not None and not isinstance(reply, str):
        raise NotificationError("reply must be a string when provided.")
    outcome = document.get("outcome", "unknown")
    if not isinstance(outcome, str) or outcome not in OUTCOME_TEXT:
        raise NotificationError("outcome must be success, failure, cancelled, blocked or unknown.")
    return "\n\n".join(messages), reply, outcome


def notification_text(text, plain_markup=False):
    """Hide local destinations/UI directives while preserving explicit web URLs."""
    newline = r"(?:\r\n|\n|\r)"
    directive = r'[ \t]*::(?:created-thread|code-comment)\{[^\r\n]*\}[ \t\\]*'
    # A terminal UI block and its separator are presentation metadata, not prose.
    text = re.sub(newline + r"(?:[ \t]*" + newline + r")*(?:" + directive
                  + r"(?:" + newline + r"|$))+[ \t\r\n]*\Z", "", text)
    text = re.sub(r"(?m)^" + directive + r"(?:" + newline + r"|$)", "", text)

    protected = []
    prefix = "\x00bark-text-"
    while prefix in text:
        prefix += "-"

    def protect(value):
        protected.append(value)
        return prefix + str(len(protected) - 1) + "\x00"

    def link(match):
        label, destination = match.group(1), match.group(2).strip()
        destination = destination[1:-1] if destination.startswith("<") and destination.endswith(">") else destination
        if re.match(r"https?://", destination, re.IGNORECASE):
            return protect(destination) if label == destination else label + " (" + protect(destination) + ")"
        return label

    # Accept normal links and the escaped opening parenthesis in copied chat text.
    text = re.sub(r"!?\[([^\]\r\n]+)\]\\?\((<[^>\r\n]+>|(?:[^()\r\n]|\([^()\r\n]*\))*)\)", link, text)
    text = re.sub(r"https?://[^\s<>\"`]+", lambda match: protect(match.group()), text, flags=re.IGNORECASE)
    text = re.sub(r"(?:codex|vscode|plugin)://[^\s<>\"`)\]}]+", "", text, flags=re.IGNORECASE)

    local_start = r"(?:[A-Za-z]:[\\/]|\\\\|file://|~/|/(?:Users|home|tmp|var|etc|opt|workspace|workspaces|mnt|private)/)"

    def filename(path):
        if path.lower().startswith("file://"):
            path = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        return re.split(r"[\\/]", path.rstrip("/\\"))[-1] or "本地目录"

    # Quoted paths can contain spaces; bare paths end at punctuation/whitespace.
    text = re.sub(r"([\"'`])(" + local_start + r"[^\r\n]*?)\1",
                  lambda match: match.group(1) + filename(match.group(2)) + match.group(1), text)
    text = re.sub(r"(?<![\w:/])" + local_start + r"[^\s\"'`()\[\]{}<>，。；！？]+",
                  lambda match: filename(match.group()), text)
    if plain_markup:
        # Protect literal code content while removing only its display delimiters.
        text = re.sub(r"(?m)^[ \t]*(`{3,}|~{3,})[^\r\n]*" + newline
                      + r"([\s\S]*?)^[ \t]*\1[ \t]*(?=\r?$)",
                      lambda match: protect(match.group(2)), text)
        text = re.sub(r"(`+)([^`\r\n]+)\1", lambda match: protect(match.group(2)), text)
        text = re.sub(r"(\*\*|__)(?=\S)([^\r\n]*?\S)\1", lambda match: match.group(2), text)
        text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+", "", text)
    # Reverse order also handles a protected code span containing a protected URL.
    for index in range(len(protected) - 1, -1, -1):
        text = text.replace(prefix + str(index) + "\x00", protected[index])
    return text


def compose_body(request_text, reply, include_reply):
    if not request_text.strip():
        raise NotificationError("Task request is empty; no notification sent.")
    if not include_reply:
        return request_text
    if not isinstance(reply, str) or not reply.strip():
        raise NotificationError("include_reply requires the complete final reply in messages JSON; no notification sent.")
    return "【你的请求】\n" + request_text + "\n\n【任务回复】\n" + reply


def make_payload(config, body, workspace):
    if not body.strip():
        raise NotificationError("Task body is empty; no notification sent.")
    workspace_path = Path(workspace).expanduser().resolve()
    if not workspace_path.is_dir():
        raise NotificationError("Workspace must be an existing task workspace directory.")
    return {
        "device_key": config["device_key"],
        "title": device_name(),
        "subtitle": workspace_path.name or str(workspace_path),
        config["content_format"]: body,
        "group": config["group"],
        "ttl": config["ttl"],
    }


def encode_payload(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def send(config, payload):
    request = urllib.request.Request(
        config["server"] + "/push",
        data=encode_payload(payload),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            status = response.status
            data = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 413:
            raise PayloadTooLarge("Bark returned HTTP 413; no further automatic retry.") from exc
        raise NotificationError("Bark returned HTTP %s; no automatic retry." % exc.code) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise NotificationError("Network failure; delivery is unknown. No automatic retry.") from exc
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise NotificationError("Invalid Bark response; delivery is unknown. No automatic retry.") from exc
    if not 200 <= status < 300 or not isinstance(result, dict) or result.get("code") != 200:
        raise NotificationError("Bark did not confirm success; no automatic retry.")
    return {"ok": True, "code": 200, "title": payload["title"],
            "subtitle": payload["subtitle"], "content_format": config["content_format"],
            "body_chars": len(payload[config["content_format"]]),
            "body_sha256": hashlib.sha256(payload[config["content_format"]].encode("utf-8")).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--messages-file", type=Path, help="UTF-8 JSON object with a messages array; recommended")
    source.add_argument("--body-file", type=Path, help="Legacy literal UTF-8 file; every newline is preserved")
    parser.add_argument("--workspace", type=Path, required=True, help="Current task workspace root, not the skill directory")
    parser.add_argument("--config", type=Path, default=SKILL_DIR / "config.json")
    parser.add_argument("--dry-run", action="store_true", help="Preview with key hidden; do not send")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.messages_file is not None:
            request_text, reply, outcome = read_messages(args.messages_file)
        else:
            try:
                request_text = args.body_file.read_bytes().decode("utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise NotificationError("Cannot read the UTF-8 task body file.") from exc
            reply = None
            outcome = "unknown"
        displayed_request = notification_text(request_text) if config["readable_body"] else request_text
        displayed_reply = (notification_text(reply, plain_markup=config["content_format"] == "body")
                           if config["readable_body"] and isinstance(reply, str) else reply)
        body = compose_body(displayed_request, displayed_reply, config["include_reply"])
        payload = make_payload(config, body, args.workspace)
        short_reply = OUTCOME_TEXT[outcome]
        can_shorten = (config["long_reply_fallback"] and config["include_reply"]
                       and displayed_reply != short_reply)
        fallback_reason = None

        def shortened_payload():
            return dict(payload, **{config["content_format"]:
                        compose_body(displayed_request, short_reply, True)})

        if can_shorten and len(encode_payload(payload)) > LONG_REPLY_PAYLOAD_BYTES:
            payload = shortened_payload()
            displayed_reply = short_reply
            fallback_reason = "size"
        if args.dry_run:
            preview = dict(payload, device_key="***")
            print(json.dumps({"dry_run": True, "url": config["server"] + "/push",
                              "payload": preview, "reply_shortened": fallback_reason is not None,
                              "fallback_reason": fallback_reason}, ensure_ascii=True))
        else:
            attempts = 1
            try:
                receipt = send(config, payload)
            except PayloadTooLarge:
                # A definite size rejection is the only permitted second attempt.
                if not can_shorten or fallback_reason is not None:
                    raise
                payload = shortened_payload()
                displayed_reply = short_reply
                fallback_reason = "http_413"
                attempts = 2
                receipt = send(config, payload)
            receipt.update(attempts=attempts, reply_shortened=fallback_reason is not None,
                           fallback_reason=fallback_reason)
            receipt["request_sha256"] = hashlib.sha256(request_text.encode("utf-8")).hexdigest()
            receipt["display_request_sha256"] = hashlib.sha256(displayed_request.encode("utf-8")).hexdigest()
            if config["include_reply"]:
                receipt["reply_sha256"] = hashlib.sha256(reply.encode("utf-8")).hexdigest()
                receipt["display_reply_sha256"] = hashlib.sha256(displayed_reply.encode("utf-8")).hexdigest()
            print(json.dumps(receipt, ensure_ascii=True))
        return 0
    except (NotificationError, ValueError, OSError) as exc:
        # Never expose raw HTTP errors, response bodies, or credential-bearing URLs.
        message = str(exc) if isinstance(exc, NotificationError) else "Invalid notification input or configuration."
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
