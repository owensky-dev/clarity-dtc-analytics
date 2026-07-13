from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "template"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

try:
    import ai_narrative
except ModuleNotFoundError:
    ai_narrative = None


class AiNarrativeTests(unittest.TestCase):
    def test_prompt_requires_fact_inference_and_validation_separation(self) -> None:
        self.assertIsNotNone(ai_narrative)
        prompt = ai_narrative.build_cro_prompt({"window": {"current_start": "2026-07-06", "current_end": "2026-07-12"}, "current": {"revenue": 100.0}})
        self.assertIn("已观察到的事实", prompt)
        self.assertIn("基于事实的推测", prompt)
        self.assertIn("仍需验证的问题", prompt)
        self.assertIn("不允许虚构", prompt)

    def test_optional_narrative_writer_keeps_deterministic_report_when_disabled(self) -> None:
        self.assertIsNotNone(ai_narrative)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "narrative.md"
            status = ai_narrative.write_optional_narrative(
                {"current": {"revenue": 1}},
                {"LLM_MODE": "off"},
                output,
            )
            self.assertEqual(status, "disabled")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
