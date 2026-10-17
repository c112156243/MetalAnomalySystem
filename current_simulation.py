"""純程式電流示範訊號，不代表感測器量測或電壓換算。"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentSimulation:
    amplitude_a: float = 1.0
    frequency_hz: float = 5.0
    offset_a: float = 0.0

    @property
    def display_range(self):
        return self.offset_a - self.amplitude_a, self.offset_a + self.amplitude_a

    def generate(self, start, count, sample_rate):
        # 使用整批索引維持分段間的相位連續，每次擷取從 t=0 開始。
        return tuple(
            self.offset_a + self.amplitude_a * math.sin(2 * math.pi * self.frequency_hz * i / sample_rate)
            for i in range(start, start + count)
        )
