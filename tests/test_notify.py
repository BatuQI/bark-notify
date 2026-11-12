"""Notification behavior with fake credentials and a mocked HTTP transport."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bark_notify", ROOT / "scripts" / "notify.py")
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


class Response(io.BytesIO):
    status = 200


class NotifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.config_path = self.workspace / "config.json"
        self.messages_path = self.workspace / "messages.json"
        self.config = {"server": "https://push.example.test", "device_key": "fake-test-only",
                       "group": "test", "ttl": 86400, "content_format": "body",
                       "include_reply": True, "readable_body": False,
                       "long_reply_fallback": True}
        self.document = {"messages": ["原始请求\r\n", "补充"], "reply": "完整结果\n",
                         "outcome": "success"}
        env = patch.dict(os.environ, {"BARK_DEVICE_NAME": "test-device"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.sent = []

    @staticmethod
    def http_error(status):
        return urllib.error.HTTPError("https://push.example.test/push", status,
                                      "test rejection", None, None)

    def invoke(self, responses=None, dry_run=False):
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        original = json.dumps(self.document, ensure_ascii=False).encode("utf-8")
        self.messages_path.write_bytes(original)
        replies = iter(responses or [None])

        def open_request(request, timeout):
            self.assertEqual(timeout, 15)
            self.sent.append(json.loads(request.data))
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            return Response(b'{"code":200}' if reply is None else reply)

        output, errors = io.StringIO(), io.StringIO()
        with patch.object(notify.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = open_request
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                result = notify.main(["--messages-file", str(self.messages_path),
                                      "--workspace", str(self.workspace),
                                      "--config", str(self.config_path)]
                                     + (["--dry-run"] if dry_run else []))
        self.assertEqual(self.messages_path.read_bytes(), original)
        self.assertNotIn("fake-test-only", output.getvalue() + errors.getvalue())
        return result, json.loads(output.getvalue() or errors.getvalue())

    def test_short_reply_preserves_content_and_sends_once(self):
        result, receipt = self.invoke()
        self.assertEqual(result, 0)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]["body"], "【你的请求】\n原始请求\r\n\n\n补充\n\n【任务回复】\n完整结果\n")
        self.assertFalse(receipt["reply_shortened"])
        self.assertEqual(receipt["attempts"], 1)

    def test_multibyte_payload_is_shortened_before_first_request(self):
        self.document["reply"] = "测试" * 700
        self.assertLess(len(self.document["reply"]), notify.LONG_REPLY_PAYLOAD_BYTES)
        result, receipt = self.invoke()
        self.assertEqual(result, 0)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(receipt["fallback_reason"], "size")
        self.assertTrue(self.sent[0]["body"].endswith("【任务回复】\n已完成"))
        self.assertEqual(receipt["reply_sha256"], hashlib.sha256(self.document["reply"].encode()).hexdigest())
        self.assertEqual(receipt["display_reply_sha256"], hashlib.sha256("已完成".encode()).hexdigest())
        self.assertEqual(receipt["body_sha256"], hashlib.sha256(self.sent[0]["body"].encode()).hexdigest())

    def test_413_retries_once_with_short_reply_only(self):
        result, receipt = self.invoke([self.http_error(413), None])
        self.assertEqual(result, 0)
        self.assertEqual(receipt["attempts"], 2)
        self.assertEqual(receipt["fallback_reason"], "http_413")
        self.assertTrue(self.sent[0]["body"].endswith(self.document["reply"]))
        self.assertTrue(self.sent[1]["body"].endswith("已完成"))
        self.assertEqual(self.sent[0]["body"].split("【任务回复】")[0],
                         self.sent[1]["body"].split("【任务回复】")[0])

    def test_second_413_stops(self):
        result, receipt = self.invoke([self.http_error(413), self.http_error(413)])
        self.assertEqual(result, 1)
        self.assertFalse(receipt["ok"])
        self.assertEqual(len(self.sent), 2)

    def test_preflight_shortened_payload_is_not_retried(self):
        self.document["reply"] = "长回复" * 1000
        result, _ = self.invoke([self.http_error(413)])
        self.assertEqual(result, 1)
        self.assertEqual(len(self.sent), 1)

    def test_uncertain_or_other_failure_does_not_retry(self):
        for error in (self.http_error(500), urllib.error.URLError("timeout"),
                      TimeoutError("timeout"), b"invalid response", b'{"code":500}'):
            with self.subTest(error=type(error).__name__):
                self.sent.clear()
                result, receipt = self.invoke([error])
                self.assertEqual(result, 1)
                self.assertFalse(receipt["ok"])
                self.assertEqual(len(self.sent), 1)

    def test_missing_option_preserves_legacy_long_reply(self):
        del self.config["long_reply_fallback"]
        self.document["reply"] = "保持完整" * 1000
        result, receipt = self.invoke()
        self.assertEqual(result, 0)
        self.assertFalse(receipt["reply_shortened"])
        self.assertTrue(self.sent[0]["body"].endswith(self.document["reply"]))

    def test_disabled_option_does_not_retry_413(self):
        self.config["long_reply_fallback"] = False
        result, _ = self.invoke([self.http_error(413)])
        self.assertEqual(result, 1)
        self.assertEqual(len(self.sent), 1)

    def test_request_only_mode_is_not_shortened(self):
        self.config["include_reply"] = False
        self.document = {"messages": ["请求" * 2000]}
        result, receipt = self.invoke()
        self.assertEqual(result, 0)
        self.assertFalse(receipt["reply_shortened"])
        self.assertEqual(self.sent[0]["body"], self.document["messages"][0])

    def test_long_request_is_preserved_even_when_fallback_is_rejected(self):
        self.document["messages"] = ["请求" * 2000]
        result, _ = self.invoke([self.http_error(413)])
        self.assertEqual(result, 1)
        self.assertEqual(len(self.sent), 1)
        self.assertIn(self.document["messages"][0], self.sent[0]["body"])

    def test_outcomes_do_not_report_failure_as_success(self):
        self.document["reply"] = "结果" * 2000
        for outcome, label in [("success", "已完成"), ("failure", "任务失败"),
                               ("cancelled", "已取消"), ("blocked", "任务被拦截"),
                               (None, "任务已结束")]:
            with self.subTest(outcome=outcome):
                self.sent.clear()
                if outcome is None:
                    self.document.pop("outcome", None)
                else:
                    self.document["outcome"] = outcome
                result, _ = self.invoke()
                self.assertEqual(result, 0)
                self.assertTrue(self.sent[0]["body"].endswith("【任务回复】\n" + label))

    def test_markdown_fallback_has_no_body_field(self):
        self.config["content_format"] = "markdown"
        result, _ = self.invoke([self.http_error(413), None])
        self.assertEqual(result, 0)
        self.assertNotIn("body", self.sent[-1])
        self.assertTrue(self.sent[-1]["markdown"].endswith("已完成"))

    def test_readable_short_content_still_cleans_only_display(self):
        self.config["readable_body"] = True
        self.document["reply"] = "**完成** [文件](C:/tmp/report.md)"
        result, _ = self.invoke()
        self.assertEqual(result, 0)
        self.assertTrue(self.sent[0]["body"].endswith("完成 文件"))

    def test_dry_run_previews_fallback_without_network(self):
        self.document["reply"] = "测试" * 2000
        result, preview = self.invoke(dry_run=True)
        self.assertEqual(result, 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(preview["payload"]["device_key"], "***")
        self.assertTrue(preview["reply_shortened"])
        self.assertTrue(preview["payload"]["body"].endswith("已完成"))

    def test_invalid_outcome_or_config_fails_before_network(self):
        self.document["outcome"] = "not-a-status"
        self.assertEqual(self.invoke()[0], 1)
        self.document["outcome"] = "success"
        self.config["long_reply_fallback"] = "yes"
        self.assertEqual(self.invoke()[0], 1)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
