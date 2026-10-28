import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import visual_sequence as vs


class VisualSequenceTests(unittest.TestCase):
    def test_identical_frames_reuse_local_ocr(self):
        from PIL import Image
        frame = Image.new("RGB", (100, 40), "white")
        ocr = Mock(return_value=[("21548", .99)])
        with patch.object(vs.time, "sleep"):
            result = vs.check_checkpoint(lambda: frame, ocr, "21548")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["ocr_calls"], 1)
        ocr.assert_called_once()

    def test_integer_normalization_preserves_wrong_characters(self):
        self.assertEqual(vs.normalize("21,548", "integer"), "21548")
        for text in ("21.548", "21,54", "2I548", "21548 extra", "21 548"):
            self.assertIsNone(vs.normalize(text, "integer"))

    def test_checkpoint_requires_two_consecutive_confident_matches(self):
        ocr = Mock(side_effect=[[("21548", .99)], [("2154", .99)],
                                [("21,548", .99)], [("21,548", .98)]])
        with patch.object(vs.time, "sleep"):
            result = vs.check_checkpoint(lambda: None, ocr, "21548", "integer")
        self.assertEqual(result["attempts"], 4)

    def test_multiple_lines_cannot_accidentally_match(self):
        with self.assertRaises(vs.VerificationError):
            vs.check_checkpoint(lambda: None, lambda _: [("21548", .99), ("other", .99)],
                                "21548", timeout=0)

    def test_low_confidence_cannot_pass(self):
        with self.assertRaises(vs.VerificationError):
            vs.check_checkpoint(lambda: None, lambda _: [("21548", .7)], "21548", timeout=0)

    def test_checkpoint_failure_blocks_later_clicks(self):
        import tempfile
        plan = {"segments": [
            {"points": [[10, 20]], "roi": [0, 0, 50, 30], "expect": "1"},
            {"points": [[30, 20]], "roi": [0, 0, 50, 30], "expect": "2"}]}
        observation = {"state": [1, "Fixture", [0, 0, 100, 100]], "captured_at": vs.time.time()}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(vs.control, "validate_window"), \
             patch("mouse.click") as click, \
             patch.object(vs, "check_checkpoint", side_effect=vs.VerificationError("wrong")), \
             patch.object(vs.ImageGrab, "grab"), patch.object(vs.time, "sleep"):
            with self.assertRaises(vs.VerificationError):
                vs.run_plan(plan, observation, directory, ocr=Mock(calls=0))
            click.assert_called_once_with(10, 20)
            self.assertEqual(vs.read_json(Path(directory)/"report.json")["status"], "stopped")

    def test_stale_observation_never_clicks(self):
        plan = {"segments": [{"points": [[10, 20]], "roi": [0, 0, 50, 30], "expect": "1"}]}
        observation = {"state": [1, "Fixture", [0, 0, 100, 100]], "captured_at": 0}
        with patch("mouse.click") as click:
            with self.assertRaises(vs.VerificationError):
                vs.run_plan(plan, observation, ".", ocr=Mock(calls=0))
            click.assert_not_called()

    def test_invalid_roi_rejected_before_input(self):
        with self.assertRaises(ValueError):
            vs.region_box([0, 0, 101, 100], (100, 100))


if __name__ == "__main__":
    unittest.main()
