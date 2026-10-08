"""雙電壓通道 NI-DAQmx 有限擷取；同一 Task 共用硬體取樣時鐘。"""

import math
import re
from dataclasses import dataclass
from datetime import datetime
from queue import Queue
from threading import Event, Thread


DAQ_DEFAULTS = {
    "channel": "Dev1/ai0",
    "channel2": "Dev1/ai1",
    "terminal_config": "DIFF",
    "min_voltage": -10.0,
    "max_voltage": 10.0,
    "sample_rate": 1000.0,
    "samples_per_channel": 1000,
}


def apply_daq_defaults(config):
    config = dict(config)
    block = config.get("daq", {})
    if isinstance(block, dict):
        config["daq"] = {**DAQ_DEFAULTS, **block}
    return config


class AcquisitionError(Exception):
    pass


class AcquisitionCancelled(Exception):
    pass


@dataclass(frozen=True)
class CaptureResult:
    voltage: tuple
    channel: str
    sample_rate: float
    terminal_config: str
    min_voltage: float
    max_voltage: float
    product_type: str
    is_simulated: bool
    completed_at: datetime
    voltage2: tuple
    channel2: str


@dataclass(frozen=True)
class CaptureProgress:
    voltage: tuple
    channel: str
    sample_rate: float
    total_samples: int
    is_simulated: bool
    voltage2: tuple
    channel2: str


def validate_settings(block):
    if not isinstance(block, dict):
        raise AcquisitionError("daq 必須是 JSON 物件。")
    settings = {**DAQ_DEFAULTS, **block}
    for key in ("channel", "channel2"):
        channel = settings[key]
        if not isinstance(channel, str) or not re.fullmatch(r"[^/,:\s]+/ai\d+", channel):
            raise AcquisitionError(f"{key} 請設定單一類比輸入通道，例如 Dev1/ai0。")
    first_device, first_ai = settings["channel"].split("/ai")
    second_device, second_ai = settings["channel2"].split("/ai")
    if first_device.casefold() != second_device.casefold():
        raise AcquisitionError("兩個電壓通道必須位於同一台 NI 裝置。")
    if int(first_ai) == int(second_ai):
        raise AcquisitionError("兩個電壓通道不可重複，請分別設定 ai0、ai1 等不同通道。")
    if settings["terminal_config"] not in ("DIFF", "RSE", "NRSE"):
        raise AcquisitionError("terminal_config 必須為 DIFF、RSE 或 NRSE。")
    for name in ("sample_rate", "min_voltage", "max_voltage"):
        value = settings[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise AcquisitionError(f"{name} 必須為有限數值。")
    if not 0 < settings["sample_rate"] <= 250000:
        raise AcquisitionError("sample_rate 必須大於 0，且不得超過 250000。")
    if not -10 <= settings["min_voltage"] < settings["max_voltage"] <= 10:
        raise AcquisitionError("電壓範圍須在 -10～10 V 內，且最小值小於最大值。")
    count = settings["samples_per_channel"]
    if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 100000:
        raise AcquisitionError("samples_per_channel 必須為 2～100000 的整數。")
    if count / settings["sample_rate"] > 60:
        raise AcquisitionError("單次擷取時間不得超過 60 秒。")
    return settings


def acquire_voltage(settings, cancel, on_progress=None):
    """硬體時鐘有限取樣；分段讀取以便關窗時取消，不用軟體 sleep 取樣。"""
    settings = validate_settings(settings)
    if cancel.is_set():
        raise AcquisitionCancelled()
    try:
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, TerminalConfiguration
        from nidaqmx.system import Device
    except ImportError as error:
        raise AcquisitionError("缺少 nidaqmx，請依 README 安裝 Python 依賴及 NI-DAQmx 驅動。") from error

    try:
        device = Device(settings["channel"].split("/")[0])
        product_type = device.product_type
        is_simulated = device.dev_is_simulated
        with nidaqmx.Task() as task:
            for channel in (settings["channel"], settings["channel2"]):
                task.ai_channels.add_ai_voltage_chan(
                    channel,
                    terminal_config=getattr(TerminalConfiguration, settings["terminal_config"]),
                    min_val=settings["min_voltage"],
                    max_val=settings["max_voltage"],
                )
            count = settings["samples_per_channel"]
            task.timing.cfg_samp_clk_timing(
                settings["sample_rate"],
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=count,
            )
            task.start()
            actual_rate = task.timing.samp_clk_rate
            values = []
            values2 = []
            chunk_size = max(1, min(count, int(actual_rate * 0.1)))
            while len(values) < count:
                if cancel.is_set():
                    raise AcquisitionCancelled()
                size = min(chunk_size, count - len(values))
                chunk = task.read(
                    number_of_samples_per_channel=size,
                    timeout=size / actual_rate + 2.0,
                )
                if (not isinstance(chunk, (list, tuple)) or len(chunk) != 2
                        or any(not isinstance(row, (list, tuple)) or len(row) != size
                               or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                          for value in row) for row in chunk)):
                    raise AcquisitionError("設備回傳的雙通道樣本數不足或包含無效數值；本批資料未採用。")
                if cancel.is_set():
                    raise AcquisitionCancelled()
                values.extend(chunk[0])
                values2.extend(chunk[1])
                if on_progress is not None:
                    on_progress(CaptureProgress(
                        tuple(chunk[0]), settings["channel"], actual_rate, count, is_simulated,
                        tuple(chunk[1]), settings["channel2"],
                    ))
            if cancel.is_set():
                raise AcquisitionCancelled()
        return CaptureResult(
            tuple(values), settings["channel"], actual_rate,
            settings["terminal_config"], settings["min_voltage"], settings["max_voltage"],
            product_type, is_simulated, datetime.now(),
            tuple(values2), settings["channel2"],
        )
    except nidaqmx.errors.DaqError as error:
        reasons = {
            -50103: "設備資源被占用，請關閉 NI MAX Test Panels 或其他擷取程式。",
            -200220: "找不到指定裝置，請確認 USB 連接與 NI MAX 裝置名稱。",
            -200170: "找不到指定通道，請確認 daq.channel 與 daq.channel2。",
            -200284: "等候取樣逾時，請確認裝置連接與取樣設定。",
        }
        reason = reasons.get(error.error_code, "請確認 NI MAX 裝置、接線、驅動及擷取設定。")
        raise AcquisitionError(f"NI-DAQmx 錯誤 {error.error_code}：{reason}") from error
    except nidaqmx.errors.DaqNotFoundError as error:
        raise AcquisitionError("找不到 NI-DAQmx 驅動，請依 README 安裝。") from error


class CaptureWorker:
    def __init__(self, settings):
        self.settings = validate_settings(settings)
        self.cancel = Event()
        self.results = Queue(maxsize=1)
        # 每段只傳送新增樣本；每通道總量受單次最多 100000 筆限制。
        self.progress = Queue()
        self.thread = Thread(target=self._run, name="ni-daq-capture", daemon=False)

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            self.results.put((acquire_voltage(
                self.settings, self.cancel, self.progress.put_nowait,
            ), None))
        except AcquisitionCancelled:
            self.results.put((None, None))
        except AcquisitionError as error:
            self.results.put((None, str(error)))
        except Exception as error:
            self.results.put((None, f"擷取失敗（{type(error).__name__}），請檢查設備與 NI-DAQmx 驅動。"))

    def is_running(self):
        return self.thread.is_alive()

    def shutdown(self):
        self.cancel.set()

    def wait(self):
        if self.thread.ident is not None:
            self.thread.join()
