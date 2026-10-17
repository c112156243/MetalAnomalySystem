"""1024 筆分段的模擬判定顯示與三圖 PNG 報告。"""

from dataclasses import dataclass
from io import BytesIO

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg


WINDOW_SIZE = 1024


@dataclass(frozen=True)
class SegmentResult:
    start: int
    stop: int
    score: float
    prediction: str


def draw_results(axes, segments, dark=False):
    axes.clear()
    foreground = "#eeeeee" if dark else "black"
    axes.set_facecolor("#111111" if dark else "white")
    axes.set_ylim(0, 1)
    axes.set_xlim(0, max(1, len(segments)) + 1)
    if segments:
        axes.vlines(range(1, len(segments) + 1), 0, 1,
                    colors=["#22bb33" if item.prediction == "OK" else "#ff3333" for item in segments],
                    linewidth=1)
        rate = sum(item.prediction == "OK" for item in segments) / len(segments)
        axes.text(0.98, 0.82, f"OK: {rate:.1%}", transform=axes.transAxes,
                  ha="right", color=foreground,
                  bbox={"facecolor": axes.get_facecolor(), "alpha": 0.85, "edgecolor": "none"})
    axes.set_xlabel("Segment (1024 samples) - simulated prediction", color=foreground, fontsize=9)
    axes.set_ylabel("Result", color=foreground, fontsize=9)
    axes.tick_params(colors=foreground, labelsize=8)
    for spine in axes.spines.values():
        spine.set_color(foreground)


class PredictionPlot(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        figure = Figure(figsize=(6, 1.6), facecolor="#111111")
        super().__init__(figure)
        self.setParent(parent)
        self.setMinimumHeight(140)
        self.axes = figure.add_subplot(111)
        figure.subplots_adjust(left=0.09, right=0.98, top=0.94, bottom=0.34)
        self.show_segments(())

    def show_segments(self, segments):
        self.segments = tuple(segments)
        draw_results(self.axes, self.segments, dark=True)
        self.draw_idle()


def render_report_png(capture, segments):
    if len(capture.voltage) < WINDOW_SIZE or len(capture.voltage) != len(capture.current):
        raise ValueError("資料未足1024筆或電壓／電流筆數不一致，無法輸出。")
    if len(segments) != len(capture.voltage) // WINDOW_SIZE:
        raise ValueError("分段判定數量與擷取資料不一致。")
    figure = Figure(figsize=(12, 8), dpi=120)
    FigureCanvasAgg(figure)
    voltage, current, result = figure.subplots(3, 1)
    voltage.plot(capture.voltage, color="blue", linewidth=0.6)
    voltage.set_ylabel("Voltage (V)")
    voltage.set_title(f"{capture.channel} | {capture.sample_rate:g} samples/s | "
                      f"{'NI simulated' if capture.is_simulated else 'DAQ measured'}", fontsize=10)
    current.plot(capture.current, color="#ef9000", linewidth=0.6)
    current.set_ylabel("Current (A)")
    current.set_title("Program simulated current (not measured)", fontsize=10)
    for axes in (voltage, current):
        axes.set_xlabel("Sample index")
        axes.set_xlim(0, len(capture.voltage) - 1)
    draw_results(result, segments)
    tail = len(capture.voltage) % WINDOW_SIZE
    figure.suptitle("Welding analysis - simulated prediction (no AI model)", fontsize=13)
    figure.text(0.5, 0.015, f"{len(capture.voltage)} samples; {len(segments)} classified segments; "
                f"{tail} trailing samples retained without classification", ha="center", fontsize=9)
    figure.tight_layout(rect=(0, 0.035, 1, 0.96))
    buffer = BytesIO()
    figure.savefig(buffer, format="png")
    return buffer.getvalue()
