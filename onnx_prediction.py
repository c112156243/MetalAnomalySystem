"""正式模型：1024 筆原值、不正規化；輸出順序 OK、NG。"""

from pathlib import Path

import numpy as np


DEFAULT_MODEL_PATH = "models/best_model.onnx"
WINDOW_SIZE = 1024


class ModelError(ValueError):
    pass


class OnnxPredictor:
    def __init__(self, model_path, base_dir):
        if not isinstance(model_path, str):
            raise ModelError("模型路徑必須為文字。")
        path = Path(model_path.strip() or DEFAULT_MODEL_PATH)
        if not path.is_absolute():
            path = Path(base_dir) / path
        if path.suffix.lower() != ".onnx" or not path.is_file():
            raise ModelError(f"找不到 ONNX 模型：{path}")
        try:
            import onnxruntime as ort
        except ImportError as error:
            raise ModelError("請先依 requirements.txt 安裝 onnxruntime。") from error
        try:
            self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        except Exception as error:
            raise ModelError("ONNX 模型載入失敗，請確認檔案完整且格式受支援。") from error
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (len(inputs) != 1 or inputs[0].type != "tensor(float)"
                or len(inputs[0].shape) != 3 or inputs[0].shape[1:] != [WINDOW_SIZE, 1]
                or isinstance(inputs[0].shape[0], int) and inputs[0].shape[0] != 1
                or len(outputs) != 1 or outputs[0].type != "tensor(float)"
                or len(outputs[0].shape) != 2 or outputs[0].shape[1] != 2):
            raise ModelError("模型須接受 float32 [1,1024,1]，輸出 [1,2] 的 OK／NG 機率。")
        self.input_name = inputs[0].name
        self.path = str(path.resolve())

    def predict(self, values):
        try:
            samples = np.asarray(values, dtype=np.float32)
        except (TypeError, ValueError, OverflowError) as error:
            raise ModelError("模型輸入必須為 1024 筆有限數值。") from error
        if samples.shape != (WINDOW_SIZE,) or not np.isfinite(samples).all():
            raise ModelError("模型輸入必須為 1024 筆有限數值。")
        try:
            probabilities = np.asarray(self.session.run(
                None, {self.input_name: samples.reshape(1, WINDOW_SIZE, 1)}
            )[0])
        except Exception as error:
            raise ModelError("ONNX 模型推論失敗，本次資料不採用。") from error
        if (probabilities.shape != (1, 2) or not np.isfinite(probabilities).all()
                or np.any(probabilities < 0) or np.any(probabilities > 1)
                or not np.isclose(probabilities.sum(), 1.0, atol=1e-5)):
            raise ModelError("模型輸出不是有效的 OK／NG 機率。")
        return float(probabilities[0, 0]), ("OK", "NG")[int(probabilities[0].argmax())]
