"""launch_agent.py supports Cursor CLI as a third agent (card #154)."""
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import launch_agent  # noqa: E402


class AgentKindTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(launch_agent.agent_kind("Cursor CLI"), "cursor")
        self.assertEqual(launch_agent.agent_kind("Cursor"), "cursor")
        self.assertEqual(launch_agent.agent_kind("Codex"), "codex")
        self.assertEqual(launch_agent.agent_kind("Codex 桌面版"), "codex")
        self.assertEqual(launch_agent.agent_kind("Claude Code"), "claude")


class CursorModelTests(unittest.TestCase):
    SAMPLE = "Available models\n\nauto - Auto\ncomposer-2.5 - Composer 2.5\ncomposer-2.5-fast - Composer 2.5 Fast\n" \
             "grok-4.7 - Grok 4.7 (current)\nclaude-opus-4-8 - Claude Opus 4.8\ngpt-5.6-sol - GPT-5.6 Sol\n"

    def test_parse_ids(self):
        ids = launch_agent.parse_model_ids(self.SAMPLE)
        self.assertIn("composer-2.5", ids)
        self.assertIn("grok-4.7", ids)
        self.assertNotIn("Available", ids)

    def test_prefers_cursor_owned(self):
        self.assertEqual(launch_agent.pick_cursor_model(self.SAMPLE), "grok-4.7")
        no_grok = self.SAMPLE.replace("grok-4.7 - Grok 4.7 (current)\n", "")
        self.assertEqual(launch_agent.pick_cursor_model(no_grok), "composer-2.5")

    def test_never_defaults_to_third_party(self):
        only_third = "claude-opus-4-8 - Claude Opus\ngpt-5.6-sol - GPT\n"
        self.assertIsNone(launch_agent.pick_cursor_model(only_third))

    def test_real_listing_2026_10_17(self):
        real = ("Available models\n\nauto - Auto (default)\ncomposer-2.5 - Composer 2.5\n"
                "cursor-grok-4.5-high - Grok 4.5\ngrok-4.7-low - Grok 4.7  Low\n"
                "grok-4.7-low-fast - Grok 4.7  Low Fast\u2028grok-4.7-medium - Grok 4.7  Medium\n"
                "grok-4.7-high-fast - Grok 4.7  High Fast\u2028grok-4.7-high - Grok 4.7  High\n"
                "claude-opus-5-5-high - Claude Opus 5.5 1M High\n")
        ids = launch_agent.parse_model_ids(real)
        self.assertIn("grok-4.7-high", ids)
        self.assertIn("grok-4.7-medium", ids)
        self.assertEqual(launch_agent.pick_cursor_model(real), "grok-4.7-high")

    def test_family_fallback_skips_fast(self):
        out = "grok-5-fast - x\ngrok-5 - y\ncomposer-3 - z\n"
        self.assertEqual(launch_agent.pick_cursor_model(out, prefs=[]), "grok-5")


class CursorCommandTests(unittest.TestCase):
    def test_cmd_is_headless_single_line(self):
        pf = launch_agent.LOGS / "card999.cursor.prompt.md"
        cmd = launch_agent.cursor_cmd(999, pf, "composer-2.5")
        for flag in ("-p", "--force", "--trust", "--output-format"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "composer-2.5")
        self.assertNotIn("\n", cmd[-1])
        self.assertIn("card999.cursor.prompt.md", cmd[-1])
        self.assertIn("card999.result.md", cmd[-1])

    def test_cmd_without_model(self):
        cmd = launch_agent.cursor_cmd(5, launch_agent.LOGS / "card5.cursor.prompt.md", None)
        self.assertNotIn("--model", cmd)


class LimitDetectionTests(unittest.TestCase):
    def test_detects_limits(self):
        for s in ["You've hit your usage limit. Upgrade to Pro+ or wait until it resets.",
                  "ERROR: You've hit your usage limit. Try again at Oct 22nd, 2026 6:01 PM.",
                  "Claude AI usage limit reached|1760000000",
                  "You've hit your limit · resets 7pm (Asia/Taipei)"]:
            self.assertIsNotNone(launch_agent.detect_limit("ok\n" + s + "\n"), s)

    def test_clean_log(self):
        self.assertIsNone(launch_agent.detect_limit("All 28 tests pass.\nresult.md written\n"))
        # Smithsonian 429s discussed in a card log are not an agent quota limit
        self.assertIsNone(launch_agent.detect_limit("Smithsonian returned 429 Too Many Requests; rate limit backoff\n"))

    def test_check_log_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.log"
            p.write_text("You've hit your usage limit\n", encoding="utf-8")
            self.assertEqual(launch_agent.check_log(str(p)), 1)
            p.write_text("done\n", encoding="utf-8")
            self.assertEqual(launch_agent.check_log(str(p)), 0)


if __name__ == "__main__":
    unittest.main()
