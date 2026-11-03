"""ONNX 輸入契約、錯誤處理與使用者模型的基本推論檢查。"""

from pathlib import Path
import unittest
from unittest.mock import Mock

import numpy as np

from onnx_prediction import DEFAULT_MODEL_PATH, ModelError, OnnxPredictor


ROOT = Path(__file__).resolve().parents[1]


class OnnxTests(unittest.TestCase):
    def predictor(self, output):
        model = OnnxPredictor.__new__(OnnxPredictor)
        model.input_name = "signal"
        model.session = Mock()
        model.session.run.return_value = [np.array(output)]
        return model

    def test_raw_values_shape_type_and_class_order(self):
        values = np.arange(1024) / 10
        for output, expected in (([[.8, .2]], "OK"), ([[.1, .9]], "NG"),
                                 ([[.5, .5]], "OK")):
            with self.subTest(output=output):
                model = self.predictor(output)
                score, label = model.predict(values)
                self.assertEqual(label, expected)
                self.assertEqual(score, output[0][0])
                sent = model.session.run.call_args.args[1]["signal"]
                self.assertEqual(sent.shape, (1, 1024, 1))
                self.assertEqual(sent.dtype, np.float32)
                np.testing.assert_array_equal(sent.flatten(), values.astype(np.float32))

    def test_invalid_samples_do_not_run(self):
        model = self.predictor([[.8, .2]])
        for samples in ([0] * 1023, [0] * 1025, [[0]] * 1024,
                        [float("nan")] * 1024, [float("inf")] * 1024):
            with self.subTest(samples_length=len(samples)), self.assertRaises(ModelError):
                model.predict(samples)
        model.session.run.assert_not_called()

    def test_invalid_output_and_runtime_failure(self):
        for output in ([[.8]], [[.8, .8]], [[-1, 2]], [[float("nan"), .2]]):
            with self.subTest(output=output), self.assertRaises(ModelError):
                self.predictor(output).predict([0] * 1024)
        model = self.predictor([[.8, .2]])
        model.session.run.side_effect = RuntimeError("test")
        with self.assertRaises(ModelError):
            model.predict([0] * 1024)

    def test_missing_file(self):
        with self.assertRaises(ModelError):
            OnnxPredictor("models/missing.onnx", ROOT)

    @unittest.skipUnless((ROOT / DEFAULT_MODEL_PATH).is_file(), "使用者模型未附於此環境")
    def test_supplied_model_cpu_inference(self):
        model = OnnxPredictor("", ROOT)
        for samples in (np.zeros(1024), np.sin(np.arange(1024) / 20)):
            score, label = model.predict(samples)
            self.assertTrue(0 <= score <= 1)
            self.assertIn(label, ("OK", "NG"))
            self.assertEqual((score, label), model.predict(samples))


if __name__ == "__main__":
    unittest.main()
