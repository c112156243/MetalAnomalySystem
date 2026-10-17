"""在 Qt 主執行緒繪製電壓與模擬電流；不改動儲存用資料。"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from current_simulation import CurrentSimulation


class SignalWaveform(QWidget):
    def __init__(self, parent=None, current_mode=False):
        super().__init__(parent)
        self.current_mode = current_mode
        self.unit = "A" if current_mode else "V"
        self.signal_name = "電流（程式模擬）" if current_mode else "電壓"
        self.setMinimumSize(360, 210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName(f"{self.signal_name}波形，橫軸為時間（秒），縱軸單位為 {self.unit}")
        title = QLabel(f"{self.signal_name} ({self.unit})", self)
        title.setStyleSheet("color: #eeeeee; background: transparent; font-size: 12px;")
        self.auto_scale = QCheckBox("Auto-scale chart", self)
        self.auto_scale.setStyleSheet("color: #eeeeee; background: transparent; font-size: 11px;")
        self.auto_scale.setChecked(True)
        self.auto_scale.setToolTip("自動縮放；取消勾選時使用本批模擬電流範圍。" if current_mode
                                  else "自動縮放；取消勾選時使用本批 DAQ 電壓範圍。")
        self.auto_scale.toggled.connect(self.update)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.auto_scale)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 0)
        layout.addLayout(header)
        layout.addStretch()
        self.clear()

    def clear(self, message="等待擷取"):
        self.values = []
        self.sample_rate = 1000.0
        self.total_samples = 1000
        self.fixed_value_range = CurrentSimulation().display_range if self.current_mode else (-10.0, 10.0)
        self.channel = ""
        self.is_simulated = None
        self.message = message
        self.update()

    def begin_capture(self, settings):
        self.clear("擷取中，等待本批資料")
        self.sample_rate = settings["sample_rate"]
        self.total_samples = settings["samples_per_channel"]
        self.channel = "程式模擬電流" if self.current_mode else settings["channel"]
        if not self.current_mode:
            self.fixed_value_range = (settings["min_voltage"], settings["max_voltage"])

    def append_progress(self, progress):
        self.values.extend(progress.current if self.current_mode else progress.voltage)
        self.sample_rate = progress.sample_rate
        self.total_samples = progress.total_samples
        self.channel = "程式模擬電流" if self.current_mode else progress.channel
        self.is_simulated = True if self.current_mode else progress.is_simulated
        if self.current_mode:
            self.fixed_value_range = progress.current_simulation.display_range
        self.message = "擷取中（預覽）"
        self.update()

    def show_capture(self, result, message="擷取完成"):
        self.values = list(result.current if self.current_mode else result.voltage)
        self.sample_rate = result.sample_rate
        self.total_samples = len(self.values)
        self.channel = "程式模擬電流" if self.current_mode else result.channel
        self.is_simulated = True if self.current_mode else result.is_simulated
        self.fixed_value_range = (result.current_simulation.display_range if self.current_mode
                                  else (result.min_voltage, result.max_voltage))
        self.message = message
        self.update()

    @property
    def sample_range(self):
        return self.total_samples - 1

    @property
    def time_range(self):
        return self.sample_range / self.sample_rate

    def value_range(self):
        if not self.auto_scale.isChecked() or not self.values:
            return self.fixed_value_range
        low, high = min(self.values), max(self.values)
        margin = max((high - low) * 0.05, 0.001)
        step = self.tick_step((high - low + 2 * margin) / 8)
        return math.floor((low - margin) / step) * step, math.ceil((high + margin) / step) * step

    @staticmethod
    def tick_step(spacing):
        base = 10 ** math.floor(math.log10(spacing))
        for factor in (1, 2, 5, 10):
            if factor * base >= spacing:
                return factor * base

    def display_points(self, width):
        """保留每個像素區間的極值與時間順序，避免大量樣本掩蓋尖峰。"""
        step = max(1, math.ceil(self.total_samples / max(1, int(width))))
        for start in range(0, len(self.values), step):
            stop = min(start + step, len(self.values))
            indices = range(start, stop)
            low = min(indices, key=self.values.__getitem__)
            high = max(indices, key=self.values.__getitem__)
            for index in sorted({start, low, high, stop - 1}):
                yield index / self.sample_rate, self.values[index]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111111"))
        font = painter.font()
        font.setPixelSize(12)
        painter.setFont(font)
        low, high = self.value_range()
        plot_height = max(1, self.height() - 96)
        step = self.tick_step((high - low) / max(2, int(plot_height / 24)))
        ticks = [i * step for i in range(math.ceil(low / step), math.floor(high / step) + 1)]
        labels = [f"{value:.5g}" for value in ticks]
        left = max(42, max(painter.fontMetrics().horizontalAdvance(v) for v in labels) + 8)
        time_labels = [f"{self.time_range * i / 4:.4g}" for i in range(5)]
        label_width = max(painter.fontMetrics().horizontalAdvance(v) for v in time_labels)
        right = max(12, label_width / 2 + 4)
        plot = QRectF(left, 30, max(1, self.width() - left - right), plot_height)
        painter.fillRect(plot, QColor("#000000"))

        painter.setPen(QColor("#eeeeee"))
        source = " · 非實測" if self.current_mode else "" if self.is_simulated is None else (
            " · NI 模擬裝置" if self.is_simulated else " · 實體裝置"
        )
        caption = f"{self.channel}{source}  {self.message}  {len(self.values)}/{self.total_samples} 筆"
        caption = painter.fontMetrics().elidedText(caption, Qt.ElideRight, self.width() - 8)
        painter.drawText(QRectF(4, self.height() - 20, self.width() - 8, 18), Qt.AlignCenter, caption)

        for value, label in zip(ticks, labels):
            y = plot.bottom() - (value - low) / (high - low) * plot.height()
            painter.drawLine(QPointF(plot.left() - 4, y), QPointF(plot.left(), y))
            painter.drawText(QRectF(0, y - 9, left - 6, 18), Qt.AlignRight | Qt.AlignVCenter, label)
        for i, label in enumerate(time_labels):
            x = plot.left() + i / 4 * plot.width()
            painter.drawLine(QPointF(x, plot.bottom()), QPointF(x, plot.bottom() + 3))
            painter.drawText(QRectF(x - right, plot.bottom() + 4, right * 2, 18),
                             Qt.AlignCenter, label)
        painter.drawText(QRectF(plot.left(), plot.bottom() + 22, plot.width(), 18),
                         Qt.AlignCenter, "時間 (s)")

        if self.values:
            painter.save()
            painter.setClipRect(plot)
            pen = QPen(QColor("#00ff00"), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            path = QPainterPath()
            for index, (seconds, value) in enumerate(self.display_points(plot.width())):
                point = QPointF(
                    plot.left() + seconds / self.time_range * plot.width(),
                    plot.bottom() - (value - low) / (high - low) * plot.height(),
                )
                if index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            if len(self.values) == 1:
                painter.drawEllipse(point, 2, 2)
            else:
                painter.drawPath(path)
            painter.restore()
        painter.end()
