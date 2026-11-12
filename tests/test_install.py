"""Isolated installation checks; no real keys and no Bark requests."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bark_install", ROOT / "scripts" / "install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "codex"
        self.target = self.home / "skills" / "bark-notify"
        self.input = Path(self.temp.name) / "settings.json"
        self.input.write_text(json.dumps({"device_key": "fake-test-only"}), encoding="utf-8")
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_install(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = install.main(["--codex-home", str(self.home), *args])
        self.assertNotIn("fake-test-only", output.getvalue())
        return status

    def test_first_install_defaults_and_manual_scope(self):
        self.assertEqual(self.run_install("--config-file", str(self.input)), 0)
        config = json.loads((self.target / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["ttl"], 86400)
        self.assertEqual(config["device_key"], "fake-test-only")
        self.assertFalse(config["long_reply_fallback"])
        self.assertFalse((self.home / "AGENTS.md").exists())
        self.assertFalse((self.target / ".git").exists())

    def test_missing_first_configuration_fails_without_copying_source_key(self):
        with patch.object(install.sys.stdin, "isatty", return_value=False):
            self.assertEqual(self.run_install(), 1)
        self.assertFalse((self.target / "config.json").exists())
        self.assertFalse((self.home / "AGENTS.md").exists())

    def test_repeat_install_preserves_settings_and_user_rules_byte_for_byte(self):
        self.assertEqual(self.run_install("--config-file", str(self.input), "--enable-default"), 0)
        config_bytes = b'{"device_key":"fake-test-only", "ttl":600, "custom_option":42}\r\n'
        (self.target / "config.json").write_bytes(config_bytes)
        agents = self.home / "AGENTS.md"
        rule_bytes = ("keep outside\r\n" + install.START + "\r\n仅我明确要求时通知，自定义规则。\r\n" + install.END).encode()
        agents.write_bytes(rule_bytes)
        with patch.object(install, "SKILL_DIR", self.target), patch("builtins.input", side_effect=AssertionError("must not prompt")):
            self.assertEqual(self.run_install(), 0)
            self.assertEqual(self.run_install("--enable-default", "--config-file", str(self.input)), 0)
        self.assertEqual((self.target / "config.json").read_bytes(), config_bytes)
        self.assertEqual(agents.read_bytes(), rule_bytes)

    def test_custom_scope_and_override_preserve_unrelated_rules(self):
        self.home.mkdir()
        override = self.home / "AGENTS.override.md"
        original = b'\xef\xbb\xbf' + '# existing\r\n'.encode()
        override.write_bytes(original)
        rules = Path(self.temp.name) / "rules.txt"
        rules.write_text("只有代码修改任务完成后通知。", encoding="utf-8")
        self.assertEqual(self.run_install("--config-file", str(self.input), "--rule-file", str(rules)), 0)
        after = override.read_bytes()
        self.assertTrue(after.startswith(original))
        self.assertIn("只有代码修改任务完成后通知。".encode(), after)
        self.assertNotIn("每个用户任务结束时发送一次通知".encode(), after)
        self.assertFalse((self.home / "AGENTS.md").exists())

    def test_first_interactive_configuration_accepts_custom_values(self):
        answers = iter(["https://push.example.test", "my-group", "172800", "markdown", "n", "n", "custom", "仅文档任务通知。"])
        with patch.object(install.sys.stdin, "isatty", return_value=True), patch("builtins.input", side_effect=lambda _: next(answers)), patch.object(install.getpass, "getpass", return_value="fake-test-only"):
            self.assertEqual(self.run_install(), 0)
        config = json.loads((self.target / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["ttl"], 172800)
        self.assertEqual(config["group"], "my-group")
        self.assertEqual(config["content_format"], "markdown")
        self.assertFalse(config["include_reply"])
        self.assertFalse(config["readable_body"])
        self.assertIn("仅文档任务通知。", (self.home / "AGENTS.md").read_text(encoding="utf-8"))

    def test_invalid_first_config_does_not_persist_or_enable(self):
        self.input.write_text('{"device_key":"fake-test-only","ttl":-1}', encoding="utf-8")
        self.assertEqual(self.run_install("--config-file", str(self.input), "--enable-default"), 1)
        self.assertFalse((self.target / "config.json").exists())
        self.assertFalse((self.home / "AGENTS.md").exists())

    def test_interactive_long_reply_fallback_is_explicitly_opted_in(self):
        answers = iter(["https://push.example.test", "test", "86400", "body",
                        "y", "y", "y", "manual"])
        with patch.object(install.sys.stdin, "isatty", return_value=True), patch("builtins.input", side_effect=lambda _: next(answers)), patch.object(install.getpass, "getpass", return_value="fake-test-only"):
            self.assertEqual(self.run_install(), 0)
        config = json.loads((self.target / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(config["long_reply_fallback"])

    def test_invalid_fallback_setting_is_not_saved(self):
        self.input.write_text('{"device_key":"fake-test-only","long_reply_fallback":"yes"}', encoding="utf-8")
        self.assertEqual(self.run_install("--config-file", str(self.input)), 1)
        self.assertFalse((self.target / "config.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
