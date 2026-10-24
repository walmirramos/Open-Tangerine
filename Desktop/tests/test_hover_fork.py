import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shift_tap import ShiftTap
from hover_resolver import unique_shell_path
from glass_design import target_at, point


class ForkTests(unittest.TestCase):
    def test_tap_once_and_repeat(self):
        gesture = ShiftTap()
        self.assertFalse(gesture.sample(True, False, 1))
        for _ in range(428):
            self.assertFalse(gesture.sample(True, False, 2))
        self.assertTrue(gesture.sample(False, False, 5.828))
        self.assertFalse(gesture.sample(False, False, 6))

    def test_combination_and_click_cancel(self):
        for elapsed in (.1, .5, 2):
            gesture = ShiftTap()
            gesture.sample(True, False, 10)
            gesture.sample(True, True, 10+elapsed)
            self.assertFalse(gesture.sample(False, False, 13))

    def test_long_hold_and_bounce(self):
        gesture = ShiftTap()
        gesture.sample(True, False, 1)
        self.assertFalse(gesture.sample(False, False, 7))
        gesture.sample(True, False, 10)
        self.assertTrue(gesture.sample(False, False, 10.1))
        gesture.sample(True, False, 10.2)
        self.assertFalse(gesture.sample(False, False, 10.3))

    def test_shell_path_not_visible_label_concatenation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'ç real.png'
            path.write_bytes(b'content')
            item = SimpleNamespace(IsFolder=False, Name='nome exibido', Path=str(path))
            self.assertEqual(unique_shell_path([item], 'nome exibido'), str(path.resolve()))
            with self.assertRaises(ValueError):
                unique_shell_path([item], 'arquivo selecionado')

    def test_ambiguous_shell_names_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            items = []
            for name in ('foto.png', 'foto.jpg'):
                path = Path(directory)/name
                path.write_bytes(b'content')
                items.append(SimpleNamespace(IsFolder=False, Name='foto', Path=str(path)))
            with self.assertRaises(ValueError):
                unique_shell_path(items, 'foto')

    def test_sector_gaps_reject_click(self):
        formats = list('abcdef')
        for index in range(6):
            self.assertEqual(target_at(point(123, index*60-90), formats), index)
            self.assertEqual(target_at(point(123, index*60-60), formats), -1)

    def test_controller_poll_dispatches_only_on_release(self):
        from unittest.mock import Mock, patch
        from PySide6.QtCore import QProcess
        from windows_main import Controller
        host = object.__new__(Controller)
        host.enabled, host.batch, host.dialog = True, None, None
        host.epoch, host.alt_was = 0, False
        host.gesture = ShiftTap()
        host.disk = Mock()
        host.disk.isVisible.return_value = False
        host.lookup = Mock()
        host.lookup.state.return_value = QProcess.NotRunning
        host.settings = Mock()
        host.settings.value.return_value = False
        host.position = lambda: (123, 456)
        host.request_hover = Mock()
        down = {0x10}
        host.held = lambda vk: vk in down
        with patch('windows_main.time.monotonic', side_effect=[10, 10.1]):
            host.poll()
            host.request_hover.assert_not_called()
            down.clear()
            host.poll()
        host.request_hover.assert_called_once_with(123, 456)

    def test_controller_typing_does_not_dispatch(self):
        from unittest.mock import Mock, patch
        from PySide6.QtCore import QProcess
        from windows_main import Controller
        host = object.__new__(Controller)
        host.enabled, host.batch, host.dialog = True, None, None
        host.epoch, host.alt_was = 0, False
        host.gesture = ShiftTap()
        host.disk = Mock()
        host.disk.isVisible.return_value = False
        host.lookup = Mock()
        host.lookup.state.return_value = QProcess.NotRunning
        host.settings = Mock()
        host.settings.value.return_value = False
        host.request_hover = Mock()
        down = {0x10, 0x41}
        host.held = lambda vk: vk in down
        with patch('windows_main.time.monotonic', side_effect=[10, 10.1]):
            host.poll()
            down.clear()
            host.poll()
        host.request_hover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
