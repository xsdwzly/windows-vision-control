import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import qwen_locate as q
import win_control_v2 as v2


class LocalizationTests(unittest.TestCase):
    def test_window_handle_is_preserved(self):
        with patch.object(q.win32gui, "EnumWindows", side_effect=lambda cb, arg: cb(777, arg)), patch.object(q.win32gui, "IsWindowVisible", return_value=True), patch.object(q.win32gui, "GetWindowText", return_value="Example"), patch.object(q, "get_physical_rect", return_value=(100, 200, 600, 500)):
            self.assertEqual(q.find_window("Example"), [(777, "Example", (100, 200, 600, 500))])

    def test_primary_dimensions_are_used(self):
        with patch.object(q, "screenshot_ps", return_value=(1920, 1080)), patch.object(q, "call_qwen3", return_value=({"button": {"cx": 50, "cy": 60}}, None, 0)) as call:
            q.locate("button", single_pass=True)
            call.assert_called_once_with("button", 1920, 1080)

    def test_window_move_during_request_discards_results(self):
        windows = [[(777, "Example", (100, 200, 600, 500))], [(777, "Example", (300, 400, 1000, 800))]]
        with patch.object(q, "find_window", side_effect=windows), patch.object(q, "screenshot_window"), patch.object(q, "call_qwen3", return_value=({"button": {"cx": 0, "cy": 0}}, None, 0)):
            with self.assertRaisesRegex(RuntimeError, "STALE"):
                q.locate("button", mode="win", window_name="Example")

    def test_duplicate_windows_never_capture(self):
        with patch.object(q, "find_window", return_value=[(1, "Example", (0,0,100,100)), (2, "Example", (0,0,100,100))]), patch.object(q, "screenshot_window") as snap:
            with self.assertRaises(RuntimeError):
                q.locate("button", mode="win", window_name="Example")
            snap.assert_not_called()

    def test_duplicate_targets_never_choose_first(self):
        with self.assertRaises(SystemExit):
            v2.choose_point([{"name": "button1"}, {"name": "button2"}])

    def test_failed_text_focus_never_clears_or_pastes(self):
        with patch.object(v2.v1, "click_xy"), patch.object(v2.time, "sleep"), patch.object(v2.v1, "require_text_focus", side_effect=SystemExit("IME")), patch.object(v2.v1, "send_ctrl_a_backspace") as clear, patch.object(v2.v1, "send_ctrl_v") as paste:
            with self.assertRaises(SystemExit):
                v2.paste_at(10, 10, "test", replace=True)
            clear.assert_not_called()
            paste.assert_not_called()

    def test_unstable_results_do_not_reach_click_selection(self):
        with patch.object(v2, "run_capture", return_value=(0, "[WARN] UNSTABLE", "")):
            with self.assertRaises(SystemExit):
                v2.locate_target("button", log=False)

    def test_missing_key_does_not_read_private_config(self):
        with patch.dict(q.os.environ, {}, clear=True), patch("builtins.open", side_effect=AssertionError("must not read config")):
            self.assertEqual(q.get_api_key(), "")


if __name__ == "__main__":
    unittest.main()
