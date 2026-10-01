import math
import time

import nidaqmx
from nidaqmx.constants import TerminalConfiguration
from nidaqmx.system import System

device = System.local().devices["Dev1"]
is_simulated = device.dev_is_simulated

print(f"裝置：{device.name}")
print(f"型號：{device.product_type}")
print(f"類型：{'模擬裝置' if is_simulated else '實體裝置'}")

values = []

with nidaqmx.Task() as task:
    task.ai_channels.add_ai_voltage_chan(
        physical_channel="Dev1/ai0",
        terminal_config=TerminalConfiguration.DIFF,
        min_val=-10.0,
        max_val=10.0,
    )

    # 不設定取樣時鐘，對應 Test Panels 的 On Demand。
    for index in range(20):
        voltage = task.read(timeout=5.0)

        if not math.isfinite(voltage):
            raise RuntimeError("收到無效數值")

        values.append(voltage)
        print(f"第 {index + 1:02d} 筆：{voltage:+.6f} V")
        time.sleep(0.1)

print(f"\nPASS：成功透過 NI-DAQmx 讀取 {len(values)} 筆資料。")
print(f"最小值：{min(values):+.6f} V")
print(f"最大值：{max(values):+.6f} V")
print("此結果只確認讀取流程成功，尚未驗證量測準確度。")