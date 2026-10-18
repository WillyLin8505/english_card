"""launch_agent.py must prepend agent_preamble.md to every prompt."""
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import launch_agent  # noqa: E402


class LaunchAgentPreambleTests(unittest.TestCase):
    def test_preamble_file_exists_and_covers_standing_rules(self):
        text = launch_agent.PREAMBLE.read_text(encoding="utf-8")
        self.assertTrue(text.strip())
        for needle in [
            "foreground",
            "10 minutes",
            "result.md",
            "127.0.0.1:5173",
            "8770",
            ".env",
            "401",
            "commit",
            "regression",
            "git stash",
            "git reset",
            "git clean",
            "working tree",
        ]:
            self.assertIn(needle, text, needle)

    def test_build_prompt_prepends_preamble(self):
        preamble = "# STANDING\nrule-one\n\n# Card prompt\n"
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "card.prompt.txt"
            prompt.write_text("CARD BODY LINE\n", encoding="utf-8")
            out = launch_agent.build_prompt(prompt, preamble=preamble)
        self.assertTrue(out.startswith(preamble))
        self.assertIn("CARD BODY LINE", out)
        self.assertLess(out.index("STANDING"), out.index("CARD BODY LINE"))

    def test_build_prompt_uses_real_preamble_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "card.prompt.txt"
            prompt.write_text("only-the-card\n", encoding="utf-8")
            out = launch_agent.build_prompt(prompt)
        head = launch_agent.load_preamble()
        self.assertTrue(out.startswith(head))
        self.assertTrue(out.endswith("only-the-card\n") or out.endswith("only-the-card"))
        self.assertIn("127.0.0.1:5173", out)
        self.assertIn("only-the-card", out)


if __name__ == "__main__":
    unittest.main()
