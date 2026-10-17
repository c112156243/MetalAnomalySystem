"""NI-DAQmx 單通道電壓有限擷取，搭配同時間座標的程式模擬電流。"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from queue import Queue
from threading import Event, Thread
from time import monotonic
from current_simulation import CurrentSimulation


DAQ_DEFAULTS = {
    "channel": "Dev1/ai0",
    "terminal_config": "DIFF",
    "min_voltage": -10.0,
    "max_voltage": 10.0,
    "sample_rate": 1000.0,
    "samples_per_channel": 1024,
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
    current: tuple
    current_simulation: CurrentSimulation = field(default_factory=CurrentSimulation)


@dataclass(frozen=True)
class CaptureProgress:
    voltage: tuple
    channel: str
    sample_rate: float
    total_samples: int
    is_simulated: bool
    current: tuple
    current_simulation: CurrentSimulation = field(default_factory=CurrentSimulation)


def validate_settings(block):
    if not isinstance(block, dict):
        raise AcquisitionError("daq 必須是 JSON 物件。")
    settings = {**DAQ_DEFAULTS, **block}
    channel = settings["channel"]
    if not isinstance(channel, str) or not re.fullmatch(r"[^/,:\s]+/ai\d+", channel):
        raise AcquisitionError("channel 請設定單一類比輸入通道，例如 Dev1/ai0。")
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
    if isinstance(count, bool) or not isinstance(count, int) or not 1024 <= count <= 100000:
        raise AcquisitionError("資料未足1024筆：取樣點數須為 1024～100000 的整數，本次不擷取。")
    if count / settings["sample_rate"] > 60:
        raise AcquisitionError("單次擷取時間不得超過 60 秒。")
    return settings


def acquire_voltage(settings, cancel, on_progress=None, stop=None):
    """內部模式有限取樣；外部模式持續讀取，stop 保留資料、cancel 捨棄。"""
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
            task.ai_channels.add_ai_voltage_chan(
                settings["channel"],
                terminal_config=getattr(TerminalConfiguration, settings["terminal_config"]),
                min_val=settings["min_voltage"],
                max_val=settings["max_voltage"],
            )
            count = settings["samples_per_channel"]
            task.timing.cfg_samp_clk_timing(
                settings["sample_rate"],
                sample_mode=AcquisitionType.CONTINUOUS if stop is not None else AcquisitionType.FINITE,
                samps_per_chan=max(count, int(settings["sample_rate"])) if stop is not None else count,
            )
            task.start()
            actual_rate = task.timing.samp_clk_rate
            if not isinstance(actual_rate, (int, float)) or not math.isfinite(actual_rate) or actual_rate <= 0:
                raise AcquisitionError("設備回報無效取樣率。")
            values = []
            current_values = []
            simulation = CurrentSimulation()
            chunk_size = max(1, min(count, int(actual_rate * 0.1)))
            limit = min(100000, int(actual_rate * 60)) if stop is not None else count
            stop_remaining = None
            started_at = monotonic()
            last_data_at = started_at
            while len(values) < limit:
                if cancel.is_set():
                    raise AcquisitionCancelled()
                size = min(chunk_size, limit - len(values))
                if stop is not None:
                    available = task.in_stream.avail_samp_per_chan
                    if stop.is_set() and stop_remaining is None:
                        # 只採用收到停止要求時已到達的樣本，不等待湊足 1024 筆。
                        stop_remaining = min(available, limit - len(values))
                    if stop_remaining is not None:
                        if stop_remaining == 0:
                            break
                        size = min(size, stop_remaining)
                    else:
                        size = min(size, available)
                    if size == 0:
                        if monotonic() - last_data_at > 2.0:
                            raise AcquisitionError("等候取樣逾時，本次資料未採用。")
                        cancel.wait(0.01)
                        continue
                chunk = task.read(
                    number_of_samples_per_channel=size,
                    timeout=size / actual_rate + 2.0,
                )
                if (not isinstance(chunk, (list, tuple)) or len(chunk) != size
                        or not all(isinstance(value, (int, float)) and math.isfinite(value)
                                   for value in chunk)):
                    raise AcquisitionError("設備回傳的電壓樣本數不足或包含無效數值；本批資料未採用。")
                if cancel.is_set():
                    raise AcquisitionCancelled()
                current_chunk = simulation.generate(len(values), size, actual_rate)
                values.extend(chunk)
                current_values.extend(current_chunk)
                last_data_at = monotonic()
                if stop_remaining is not None:
                    stop_remaining -= size
                if on_progress is not None:
                    on_progress(CaptureProgress(
                        tuple(chunk), settings["channel"], actual_rate,
                        max(count, len(values)) if stop is not None else count, is_simulated,
                        current_chunk, simulation,
                    ))
            if cancel.is_set():
                raise AcquisitionCancelled()
            if len(values) < 1024:
                raise AcquisitionError(f"資料未足1024筆（本次 {len(values)} 筆），不判定、不儲存，請重新擷取。")
        return CaptureResult(
            tuple(values), settings["channel"], actual_rate,
            settings["terminal_config"], settings["min_voltage"], settings["max_voltage"],
            product_type, is_simulated, datetime.now(),
            tuple(current_values), simulation,
        )
    except nidaqmx.errors.DaqError as error:
        reasons = {
            -50103: "設備資源被占用，請關閉 NI MAX Test Panels 或其他擷取程式。",
            -200220: "找不到指定裝置，請確認 USB 連接與 NI MAX 裝置名稱。",
            -200170: "找不到指定通道，請確認 daq.channel。",
            -200284: "等候取樣逾時，請確認裝置連接與取樣設定。",
        }
        reason = reasons.get(error.error_code, "請確認 NI MAX 裝置、接線、驅動及擷取設定。")
        raise AcquisitionError(f"NI-DAQmx 錯誤 {error.error_code}：{reason}") from error
    except nidaqmx.errors.DaqNotFoundError as error:
        raise AcquisitionError("找不到 NI-DAQmx 驅動，請依 README 安裝。") from error


class CaptureWorker:
    def __init__(self, settings, continuous=False):
        self.settings = validate_settings(settings)
        self.cancel = Event()
        self.stop = Event() if continuous else None
        self.results = Queue(maxsize=1)
        # 每段只傳送新增樣本；每通道總量受單次最多 100000 筆限制。
        self.progress = Queue()
        self.thread = Thread(target=self._run, name="ni-daq-capture", daemon=False)

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            args = (self.settings, self.cancel, self.progress.put_nowait)
            result = acquire_voltage(*args) if self.stop is None else acquire_voltage(*args, stop=self.stop)
            self.results.put((result, None))
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

    def finish(self):
        if self.stop is not None:
            self.stop.set()

    def wait(self):
        if self.thread.ident is not None:
            self.thread.join()
