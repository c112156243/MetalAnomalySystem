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
        self.values = [math.sin(i / 20) for i in range(1024)]
        self.offset = 0

        def read(number_of_samples_per_channel, timeout):
            start = self.offset
            self.offset += number_of_samples_per_channel
            return self.values[start:self.offset]

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
        self.assertEqual(len(result.current), len(self.values))
        self.assertAlmostEqual(result.current[50], 1.0)
        self.assertAlmostEqual(result.current[150], -1.0)
        self.assertFalse(result.is_simulated)
        self.assertEqual(result.channel, "Dev1/ai0")
        self.assertEqual(self.task.ai_channels.add_ai_voltage_chan.call_args_list, [
            call(channel, terminal_config=TerminalConfiguration.DIFF, min_val=-10.0, max_val=10.0)
            for channel in ("Dev1/ai0",)
        ])
        self.factory.assert_called_once()
        self.task.timing.cfg_samp_clk_timing.assert_called_once_with(
            1000.0, sample_mode=AcquisitionType.FINITE, samps_per_chan=1024)
        self.task.start.assert_called_once()
        self.context.__exit__.assert_called_once()

    def test_partial_last_chunk_and_actual_coerced_rate(self):
        self.task.timing.samp_clk_rate = 999.0
        result = daq.acquire_voltage({"samples_per_channel": 1024}, Event())
        self.assertEqual(result.voltage, tuple(self.values[:1024]))
        self.assertEqual(len(result.current), 1024)
        self.assertAlmostEqual(result.current[200], math.sin(2 * math.pi * 5 * 200 / 999))
        self.assertEqual(result.sample_rate, 999.0)
        sizes = [c.kwargs["number_of_samples_per_channel"] for c in self.task.read.call_args_list]
        self.assertEqual(sizes, [99] * 10 + [34])

    def test_progress_delivers_new_samples_with_actual_rate_before_completion(self):
        self.task.timing.samp_clk_rate = 999.0
        received = []

        def progress(chunk):
            self.context.__exit__.assert_not_called()
            received.append(chunk)

        result = daq.acquire_voltage({"samples_per_channel": 1024}, Event(), progress)
        self.assertEqual([len(p.voltage) for p in received], [99] * 10 + [34])
        self.assertEqual(tuple(v for p in received for v in p.voltage), result.voltage)
        self.assertEqual(tuple(v for p in received for v in p.current), result.current)
        self.assertEqual(result.current, daq.CurrentSimulation().generate(0, 1024, 999))
        self.assertTrue(all(p.sample_rate == 999.0 and p.total_samples == 1024 for p in received))
        self.assertTrue(all(p.channel == "Dev1/ai0" and not p.is_simulated for p in received))

    def test_invalid_and_cancelled_chunks_are_not_published(self):
        progress = Mock()
        self.task.read.side_effect = None
        self.task.read.return_value = [float("nan")] * 100
        with self.assertRaises(daq.AcquisitionError):
            daq.acquire_voltage({}, Event(), progress)
        progress.assert_not_called()
        cancel = Event()

        def read(**kwargs):
            cancel.set()
            return [0.2] * kwargs["number_of_samples_per_channel"]

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
        for values in ([float("nan")] * 100, [float("inf")] * 100,
                       [0.0] * 99, [[0.0] * 100], [None] * 100, ["bad"] * 100):
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
            return [0.2] * kwargs["number_of_samples_per_channel"]

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
                      {"samples_per_channel": 1000}, {"samples_per_channel": 1023},
                      {"samples_per_channel": 100001}, {"sample_rate": 1},
                      {"min_voltage": 10}, {"max_voltage": 11},
                      {"terminal_config": "bad"}, {"channel": "Dev1/ai0:1"}]:
            with self.subTest(block=block):
                with self.assertRaises(daq.AcquisitionError):
                    daq.acquire_voltage(block, Event())
        self.factory.assert_not_called()

    def test_external_stop_reads_only_available_samples_and_keeps_tail(self):
        stop = Event()
        stop.set()
        self.values = [index / 10000 for index in range(2150)]
        self.task.in_stream.avail_samp_per_chan = 2150
        result = daq.acquire_voltage({}, Event(), stop=stop)
        self.assertEqual(result.voltage, tuple(self.values))
        self.assertEqual(result.current, daq.CurrentSimulation().generate(0, 2150, 1000))
        self.assertEqual(self.offset, 2150)
        self.assertEqual(self.task.timing.cfg_samp_clk_timing.call_args.kwargs["sample_mode"],
                         AcquisitionType.CONTINUOUS)
        self.context.__exit__.assert_called_once()

    def test_external_short_stop_rejects_without_waiting_for_full_window(self):
        for available in (0, 300, 1023):
            with self.subTest(available=available):
                self.offset = 0
                stop = Event()
                stop.set()
                self.task.in_stream.avail_samp_per_chan = available
                with self.assertRaisesRegex(daq.AcquisitionError, "資料未足1024筆"):
                    daq.acquire_voltage({}, Event(), stop=stop)
                self.assertEqual(self.offset, available)

    def test_external_continuous_stop_and_cancel_are_distinct(self):
        stop, cancel = Event(), Event()
        self.task.in_stream.avail_samp_per_chan = 100
        def progress(chunk):
            if self.offset >= 1100:
                stop.set()
        self.values = [0.2] * 2000
        result = daq.acquire_voltage({}, cancel, progress, stop=stop)
        self.assertEqual(len(result.voltage), 1200)
        self.offset = 0
        stop.clear()
        with self.assertRaises(daq.AcquisitionCancelled):
            daq.acquire_voltage({}, cancel, lambda chunk: cancel.set(), stop=stop)

    def test_external_missing_samples_times_out_and_releases_task(self):
        self.task.in_stream.avail_samp_per_chan = 0
        with patch.object(daq, "monotonic", side_effect=[0.0, 3.0]):
            with self.assertRaisesRegex(daq.AcquisitionError, "逾時"):
                daq.acquire_voltage({}, Event(), stop=Event())
        self.context.__exit__.assert_called_once()

    def test_external_limit_finishes_at_60_seconds_of_samples(self):
        self.task.timing.samp_clk_rate = 20.0
        self.values = [0.1] * 2000
        self.task.in_stream.avail_samp_per_chan = 100
        result = daq.acquire_voltage({}, Event(), stop=Event())
        self.assertEqual(len(result.voltage), 1200)

    def test_single_sample_chunks_preserve_voltage_and_current_pairing(self):
        self.task.timing.samp_clk_rate = 2.0
        result = daq.acquire_voltage({"sample_rate": 1000, "samples_per_channel": 1024}, Event())
        self.assertEqual(result.voltage, tuple(self.values[:1024]))
        self.assertEqual(result.current, daq.CurrentSimulation().generate(0, 1024, 2))
        self.assertTrue(all(c.kwargs["number_of_samples_per_channel"] == 1
                            for c in self.task.read.call_args_list))

    def test_voltage_failure_after_preview_discards_entire_batch(self):
        self.task.read.side_effect = [
            [0.1] * 100, [float("nan")] * 100,
        ]
        progress = Mock()
        with self.assertRaises(daq.AcquisitionError):
            daq.acquire_voltage({}, Event(), progress)
        progress.assert_called_once()
        self.context.__exit__.assert_called_once()

    def test_legacy_channel2_is_preserved_but_not_used_for_hardware(self):
        settings = daq.apply_daq_defaults({"daq": {"channel2": "MissingDevice/ai99"}})["daq"]
        self.assertEqual(settings["channel2"], "MissingDevice/ai99")
        result = daq.acquire_voltage(settings, Event())
        self.task.ai_channels.add_ai_voltage_chan.assert_called_once()
        self.assertEqual(self.task.ai_channels.add_ai_voltage_chan.call_args.args[0], "Dev1/ai0")
        self.assertEqual(len(result.current), 1024)

    def test_current_is_independent_of_voltage_and_restarts_each_capture(self):
        self.task.read.side_effect = lambda **kwargs: [0.0] * kwargs["number_of_samples_per_channel"]
        first = daq.acquire_voltage({}, Event())
        self.task.read.side_effect = lambda **kwargs: [9.0] * kwargs["number_of_samples_per_channel"]
        second = daq.acquire_voltage({}, Event())
        self.assertEqual(first.current, second.current)
        self.assertNotEqual(first.voltage, second.voltage)
        self.assertEqual(first.current[0], 0.0)

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
