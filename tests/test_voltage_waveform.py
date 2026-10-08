"""波形座標、尖峰保留與 Qt 繪圖檢查，不使用設備。"""

import os
import unittest
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from daq_acquisition import CaptureProgress, CaptureResult, DAQ_DEFAULTS
from voltage_waveform import VoltageWaveform


class WaveformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.plot = VoltageWaveform()
        self.plot.resize(700, 180)
        self.addCleanup(self.close_plot)

    def close_plot(self):
        self.plot.close()
        self.plot.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_time_coordinates_follow_actual_rate_and_dc_range_is_nonzero(self):
        self.plot.append_progress(CaptureProgress((0.002,) * 4, "Dev1/ai0", 2, 6, False,
                                                 (-0.002,) * 4, "Dev1/ai1"))
        self.assertEqual(self.plot.time_range, 2.5)
        self.assertEqual(list(self.plot.display_points(700)),
                         [(0, 0.002), (0.5, 0.002), (1, 0.002), (1.5, 0.002)])
        low, high = self.plot.voltage_range()
        self.assertLess(low, 0.002)
        self.assertGreater(high, 0.002)
        self.assertFalse(self.plot.grab().isNull())

    def test_large_batch_display_preserves_spikes_order_endpoints_and_raw_data(self):
        values = [0.0] * 100000
        values[127], values[128] = 9.5, -8.5
        self.plot.append_progress(CaptureProgress(tuple(values), "Dev1/ai0", 250000, 100000, False,
                                                 (0.1,) * 100000, "Dev1/ai1"))
        points = list(self.plot.display_points(600))
        self.assertLessEqual(len(points), 4 * 600)
        self.assertIn((127 / 250000, 9.5), points)
        self.assertIn((128 / 250000, -8.5), points)
        self.assertEqual(points, sorted(points))
        self.assertEqual(points[0], (0, 0))
        self.assertEqual(points[-1], (99999 / 250000, 0))
        self.assertEqual(self.plot.voltage, values)
        self.assertFalse(self.plot.grab().isNull())

    def test_empty_and_single_sample_preview_render(self):
        self.assertFalse(self.plot.grab().isNull())
        self.plot.append_progress(CaptureProgress((-0.025,), "Dev1/ai0", 1, 2, True,
                                                 (0.025,), "Dev1/ai1"))
        self.assertEqual(list(self.plot.display_points(600)), [(0, -0.025)])
        self.assertFalse(self.plot.grab().isNull())

    def test_auto_scale_toggle_preserves_data_and_uses_each_capture_range(self):
        self.plot.begin_capture({**DAQ_DEFAULTS, "min_voltage": -5, "max_voltage": 5})
        self.plot.append_progress(CaptureProgress((-0.03, 0.04), "Dev1/ai0", 1000, 1000, False,
                                                 (0.03, -0.04), "Dev1/ai1"))
        self.assertTrue(self.plot.auto_scale.isChecked())
        low, high = self.plot.voltage_range()
        self.assertLessEqual(low, -0.03)
        self.assertGreaterEqual(high, 0.04)
        self.assertLess(high - low, 0.2)
        self.plot.auto_scale.click()
        self.assertEqual(self.plot.voltage_range(), (-5, 5))
        self.assertEqual(self.plot.voltage, [-0.03, 0.04])
        self.plot.show_capture(CaptureResult(
            (-0.1, 0.1), "Dev1/ai0", 1000, "DIFF", -2, 2, "USB-6211", False, datetime.now(),
            (0.2, -0.2), "Dev1/ai1",
        ))
        self.assertEqual(self.plot.voltage_range(), (-2, 2))
        self.plot.begin_capture(DAQ_DEFAULTS)
        self.assertFalse(self.plot.auto_scale.isChecked())
        self.assertEqual(self.plot.voltage_range(), (-10, 10))
        self.plot.auto_scale.click()
        self.assertTrue(self.plot.auto_scale.isChecked())


if __name__ == "__main__":
    unittest.main()
