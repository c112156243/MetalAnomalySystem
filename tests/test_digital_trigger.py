"""數位輸入與輸出皆 mock，不操作實體設備。"""

import unittest
from unittest.mock import Mock, patch

from daq_acquisition import AcquisitionError, apply_daq_defaults
from digital_trigger import ButtonDebouncer, DigitalWorker
from engineering_settings import apply_engineering_defaults, validate_engineering


class DigitalTests(unittest.TestCase):
    def config(self):
        config = apply_engineering_defaults(apply_daq_defaults({}))
        config["engineering"]["trigger_mode"] = 1
        return config

    def test_usb6211_range_and_any_high_defaults(self):
        settings, lines = validate_engineering(self.config())
        self.assertEqual(lines, [0, 1, 2, 3])
        self.assertEqual(settings["trigger_line"], "any")
        self.assertIs(settings["active_high"], True)
        self.assertEqual(settings["do_channel"], "")
        for changes in ({"di_channel": "Dev1/port0/line0:7"},
                        {"di_channel": "Dev2/port0/line0:3"},
                        {"do_channel": "Dev1/port0/line0"},
                        {"active_high": None}, {"trigger_mode": True}):
            config = self.config()
            config["engineering"].update(changes)
            with self.assertRaises(AcquisitionError):
                validate_engineering(config)

    def test_initial_held_button_and_bounce_do_not_start_capture(self):
        button = ButtonDebouncer()
        for value, timestamp in ((True, 0), (True, .1), (False, .2), (True, .22),
                                 (False, .3), (False, .4)):
            self.assertIsNone(button.update(value, timestamp))
        self.assertIsNone(button.update(True, .5))
        self.assertEqual(button.update(True, .6), "pressed")
        self.assertIsNone(button.update(True, .8))
        self.assertIsNone(button.update(False, .9))
        self.assertEqual(button.update(False, 1.0), "released")

    def test_any_line_high_and_all_low_generate_one_press_and_release(self):
        settings, lines = validate_engineering(self.config())
        worker = DigitalWorker(settings, lines)
        levels = [[False] * 4, [False] * 4,
                  [False, True, False, False], [False, True, False, False],
                  [False, False, False, True], [False, False, False, True],
                  [False] * 4, [False] * 4]
        task = Mock()
        def read(**kwargs):
            value = levels.pop(0)
            if not levels:
                worker.cancel.set()
            return value
        task.read.side_effect = read
        context = Mock(__enter__=Mock(return_value=task), __exit__=Mock(return_value=False))
        with patch("nidaqmx.Task", return_value=context), patch(
                "digital_trigger.monotonic", side_effect=[i * .1 for i in range(8)]):
            worker._run()
        self.assertEqual([worker.events.get_nowait()[0] for _ in range(worker.events.qsize())],
                         ["ready", "pressed", "released"])
        self.assertEqual(task.di_channels.add_di_chan.call_args.args[0], "Dev1/port0/line0:3")
        context.__exit__.assert_called_once()

    def test_output_latches_and_shutdown_writes_off(self):
        settings, lines = validate_engineering(self.config())
        settings.update(trigger_mode=0, do_channel="Dev1/port1/line0")
        worker = DigitalWorker(settings, lines)
        task = Mock()
        di = Mock()
        di.read.return_value = [False] * 4
        di_context = Mock(__enter__=Mock(return_value=di), __exit__=Mock(return_value=False))
        context = Mock(__enter__=Mock(return_value=task), __exit__=Mock(return_value=False))
        states = [True, True, False]
        def wait(seconds):
            if states:
                worker.alarm.set() if states.pop(0) else worker.alarm.clear()
            else:
                worker.cancel.set()
        with patch("nidaqmx.Task", side_effect=[di_context, context]), patch.object(worker.cancel, "wait", side_effect=wait):
            worker._run()
        self.assertEqual([call.args[0] for call in task.write.call_args_list], [False, True, False, False])
        context.__exit__.assert_called_once()
        di_context.__exit__.assert_called_once()

    def test_io_failure_reports_error_and_releases(self):
        settings, lines = validate_engineering(self.config())
        settings["do_channel"] = "Dev1/port1/line0"
        worker = DigitalWorker(settings, lines)
        di, do = Mock(), Mock()
        di.read.side_effect = RuntimeError("private detail")
        contexts = [Mock(__enter__=Mock(return_value=task), __exit__=Mock(return_value=False))
                    for task in (di, do)]
        with patch("nidaqmx.Task", side_effect=contexts):
            worker._run()
        messages = [worker.events.get_nowait() for _ in range(worker.events.qsize())]
        self.assertEqual(messages[-1][0], "error")
        self.assertNotIn("private detail", messages[-1][1])
        self.assertFalse(do.write.call_args.args[0])
        for context in contexts:
            context.__exit__.assert_called_once()
