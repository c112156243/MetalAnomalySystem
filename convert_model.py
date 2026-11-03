import os
from pathlib import Path

os.environ["KERAS_BACKEND"] = "tensorflow"

import keras
import numpy as np
import onnx
import onnxruntime as ort

source = Path(
    r"C:\Formal_Model_ValAcc_99p62_20261007"
    r"\Formal_Model_ValAcc_99p62_20261007\best_model.keras"
)
target = Path(__file__).resolve().parent / "models" / "best_model.onnx"

if target.exists():
    raise FileExistsError(f"輸出已存在，請先確認：{target}")

model = keras.models.load_model(source, compile=False, safe_mode=True)

assert tuple(model.input_shape) == (None, 1024, 1)
assert tuple(model.output_shape) == (None, 2)

target.parent.mkdir(parents=True, exist_ok=True)
model.export(
    str(target),
    format="onnx",
    input_signature=[
        keras.InputSpec(shape=(None, 1024, 1), dtype="float32")
    ],
    opset_version=17,
)

onnx.checker.check_model(str(target))
session = ort.InferenceSession(
    str(target), providers=["CPUExecutionProvider"]
)
input_name = session.get_inputs()[0].name

# 僅檢查轉檔一致性；正式驗收還需使用真實 OK／NG 波形。
rng = np.random.default_rng(42)
for x in (
    np.zeros((1, 1024, 1), dtype=np.float32),
    rng.normal(size=(1, 1024, 1)).astype(np.float32),
):
    expected = model(x, training=False).numpy()
    actual = session.run(None, {input_name: x})[0]

    assert actual.shape == (1, 2)
    assert np.isfinite(expected).all() and np.isfinite(actual).all()
    np.testing.assert_allclose(
        actual, expected, rtol=1e-4, atol=1e-5
    )
    np.testing.assert_array_equal(
        actual.argmax(axis=1), expected.argmax(axis=1)
    )

print(f"轉檔與基本一致性檢查通過：{target}")