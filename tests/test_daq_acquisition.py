"""DAQ API mock 測試：不接觸硬體、不寄信。"""

import math
import unittest
from threading import Event
from unittest.mock import Mock, call, patch

import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration

import daq_acquisition as daq


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.task = Mock()
        self.task.timing.samp_clk_rate = 1000.0
        self.values = [math.sin(i / 20) for i in range(1000)]
        self.values2 = [0.5 * math.cos(i / 30) for i in range(1000)]
        self.offset = 0

        def read(number_of_samples_per_channel, timeout):
            start = self.offset
            self.offset += number_of_samples_per_channel
            return [self.values[start:self.offset], self.values2[start:self.offset]]

        self.task.read.side_effect = read
        self.context = Mock()
        self.context.__enter__ = Mock(return_value=self.task)
        self.context.__exit__ = Mock(return_value=False)
        task_patch = patch("nidaqmx.Task", return_value=self.context)
        self.factory = task_patch.start()
        self.addCleanup(task_patch.stop)
        device_patch = patch("nidaqmx.system.Device", return_value=Mock(
            product_type="USB-6211", dev_is_simulated=False))
        device_patch.start()
        self.addCleanup(device_patch.stop)

    def test_finite_capture_exact_values_settings_and_release(self):
        result = daq.acquire_voltage(daq.DAQ_DEFAULTS, Event())
        self.assertEqual(result.voltage, tuple(self.values))
        self.assertEqual(result.voltage2, tuple(self.values2))
        self.assertEqual(result.channel2, "Dev1/ai1")
        self.assertFalse(result.is_simulated)
        self.assertEqual(result.channel, "Dev1/ai0")
        self.assertEqual(self.task.ai_channels.add_ai_voltage_chan.call_args_list, [
            call(channel, terminal_config=TerminalConfiguration.DIFF, min_val=-10.0, max_val=10.0)
            for channel in ("Dev1/ai0", "Dev1/ai1")
        ])
        self.factory.assert_called_once()
        self.task.timing.cfg_samp_clk_timing.assert_called_once_with(
            1000.0, sample_mode=AcquisitionType.FINITE, samps_per_chan=1000)
        self.task.start.assert_called_once()
        self.context.__exit__.assert_called_once()

    def test_partial_last_chunk_and_actual_coerced_rate(self):
        self.task.timing.samp_clk_rate = 999.0
        result = daq.acquire_voltage({"samples_per_channel": 250}, Event())
        self.assertEqual(result.voltage, tuple(self.values[:250]))
        self.assertEqual(result.voltage2, tuple(self.values2[:250]))
        self.assertEqual(result.sample_rate, 999.0)
        sizes = [c.kwargs["number_of_samples_per_channel"] for c in self.task.read.call_args_list]
        self.assertEqual(sizes, [99, 99, 52])

    def test_progress_delivers_new_samples_with_actual_rate_before_completion(self):
        self.task.timing.samp_clk_rate = 999.0
        received = []

        def progress(chunk):
            self.context.__exit__.assert_not_called()
            received.append(chunk)

        result = daq.acquire_voltage({"samples_per_channel": 250}, Event(), progress)
        self.assertEqual([len(p.voltage) for p in received], [99, 99, 52])
        self.assertEqual(tuple(v for p in received for v in p.voltage), result.voltage)
        self.assertEqual(tuple(v for p in received for v in p.voltage2), result.voltage2)
        self.assertTrue(all(p.channel2 == "Dev1/ai1" for p in received))
        self.assertTrue(all(p.sample_rate == 999.0 and p.total_samples == 250 for p in received))
        self.assertTrue(all(p.channel == "Dev1/ai0" and not p.is_simulated for p in received))

    def test_invalid_and_cancelled_chunks_are_not_published(self):
        progress = Mock()
        self.task.read.side_effect = None
        self.task.read.return_value = [[0.1] * 100, [float("nan")] * 100]
        with self.assertRaises(daq.AcquisitionError):
            daq.acquire_voltage({}, Event(), progress)
        progress.assert_not_called()
        cancel = Event()

        def read(**kwargs):
            cancel.set()
            return [[0.2] * kwargs["number_of_samples_per_channel"],
                    [0.3] * kwargs["number_of_samples_per_channel"]]

        self.task.read.side_effect = read
        with self.assertRaises(daq.AcquisitionCancelled):
            daq.acquire_voltage({}, cancel, progress)
        progress.assert_not_called()

    def test_worker_publishes_all_chunks_without_ui_consumer(self):
        worker = daq.CaptureWorker({})
        worker.start()
        worker.wait()
        result, error = worker.results.get_nowait()
        self.assertIsNone(error)
        received = []
        while not worker.progress.empty():
            received.extend(worker.progress.get_nowait().voltage)
        self.assertEqual(tuple(received), result.voltage)

    def test_invalid_or_short_data_rejected_and_task_released(self):
        for values in ([[float("nan")] * 100, [0.0] * 100],
                       [[0.0] * 100, [float("inf")] * 100],
                       [[0.0] * 100, [0.0] * 99], [[0.0] * 100],
                       [[0.0] * 99, [0.0] * 100], [0.0] * 100):
            with self.subTest(values=values[:1]):
                self.task.read.side_effect = None
                self.task.read.return_value = values
                with self.assertRaises(daq.AcquisitionError):
                    daq.acquire_voltage({}, Event())
        self.assertEqual(self.context.__exit__.call_count, 6)

    def test_cancel_during_read_discards_partial_data_and_releases_task(self):
        cancel = Event()

        def read(**kwargs):
            cancel.set()
            return [[0.2] * kwargs["number_of_samples_per_channel"],
                    [0.3] * kwargs["number_of_samples_per_channel"]]

        self.task.read.side_effect = read
        with self.assertRaises(daq.AcquisitionCancelled):
            daq.acquire_voltage({}, cancel)
        self.assertEqual(self.task.read.call_count, 1)
        self.context.__exit__.assert_called_once()

    def test_cancel_before_start_does_not_touch_hardware(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(daq.AcquisitionCancelled):
            daq.acquire_voltage({}, cancel)
        self.factory.assert_not_called()

    def test_daq_errors_are_classified_and_released(self):
        for code, message in [(-50103, "占用"), (-200220, "裝置"),
                              (-200170, "通道"), (-200284, "逾時"), (-999, "NI-DAQmx")]:
            with self.subTest(code=code):
                self.task.read.side_effect = nidaqmx.errors.DaqError("test error", code)
                with self.assertRaisesRegex(daq.AcquisitionError, message):
                    daq.acquire_voltage({}, Event())
        self.assertEqual(self.context.__exit__.call_count, 5)

    def test_missing_driver_reports_actionable_error(self):
        with patch("nidaqmx.system.Device", side_effect=nidaqmx.errors.DaqNotFoundError()):
            with self.assertRaisesRegex(daq.AcquisitionError, "驅動"):
                daq.acquire_voltage({}, Event())

    def test_missing_package_reports_actionable_error(self):
        with patch.dict("sys.modules", {"nidaqmx": None}):
            with self.assertRaisesRegex(daq.AcquisitionError, "缺少 nidaqmx"):
                daq.acquire_voltage({}, Event())

    def test_bad_config_never_starts_device(self):
        for block in [None, {"sample_rate": 0}, {"sample_rate": True},
                      {"sample_rate": float("nan")}, {"sample_rate": 250001},
                      {"samples_per_channel": 1}, {"samples_per_channel": 1.5},
                      {"samples_per_channel": 100001}, {"sample_rate": 1},
                      {"min_voltage": 10}, {"max_voltage": 11},
                      {"terminal_config": "bad"}, {"channel": "Dev1/ai0:1"},
                      {"channel2": "Dev1/ai0"}, {"channel2": "Dev1/ai00"},
                      {"channel2": "Dev2/ai1"}, {"channel2": "Dev1/ai1:2"},
                      {"channel2": None}]:
            with self.subTest(block=block):
                with self.assertRaises(daq.AcquisitionError):
                    daq.acquire_voltage(block, Event())
        self.factory.assert_not_called()

    def test_single_sample_chunks_preserve_both_channel_order(self):
        self.task.timing.samp_clk_rate = 2.0
        result = daq.acquire_voltage({"sample_rate": 2, "samples_per_channel": 2}, Event())
        self.assertEqual(result.voltage, tuple(self.values[:2]))
        self.assertEqual(result.voltage2, tuple(self.values2[:2]))
        self.assertTrue(all(c.kwargs["number_of_samples_per_channel"] == 1
                            for c in self.task.read.call_args_list))

    def test_second_channel_failure_after_preview_discards_entire_batch(self):
        self.task.read.side_effect = [
            [[0.1] * 100, [0.2] * 100], [[0.3] * 100, [float("nan")] * 100],
        ]
        progress = Mock()
        with self.assertRaises(daq.AcquisitionError):
            daq.acquire_voltage({}, Event(), progress)
        progress.assert_called_once()
        self.context.__exit__.assert_called_once()

    def test_worker_snapshots_config_and_reports_unexpected_error(self):
        settings = dict(daq.DAQ_DEFAULTS)
        worker = daq.CaptureWorker(settings)
        settings["channel"] = "Dev2/ai0"
        with patch.object(daq, "acquire_voltage", side_effect=RuntimeError("private detail")) as acquire:
            worker.start()
            worker.wait()
        result, error = worker.results.get_nowait()
        self.assertIsNone(result)
        self.assertIn("RuntimeError", error)
        self.assertNotIn("private detail", error)
        self.assertEqual(acquire.call_args.args[0]["channel"], "Dev1/ai0")


if __name__ == "__main__":
    unittest.main()
