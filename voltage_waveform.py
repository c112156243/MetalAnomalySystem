"""在 Qt 主執行緒繪製本批電壓；不改動用於判定與儲存的原始資料。"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class VoltageWaveform(QWidget):
    def __init__(self, parent=None, second_channel=False):
        super().__init__(parent)
        self.second_channel = second_channel
        self.setMinimumSize(360, 210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("電壓波形，橫軸為擷取開始後的時間（秒），縱軸為電壓（V）")
        title = QLabel("電壓 (V)", self)
        title.setStyleSheet("color: #eeeeee; background: transparent; font-size: 12px;")
        self.auto_scale = QCheckBox("Auto-scale chart", self)
        self.auto_scale.setStyleSheet("color: #eeeeee; background: transparent; font-size: 11px;")
        self.auto_scale.setChecked(True)
        self.auto_scale.setToolTip("自動縮放電壓軸；取消勾選時使用本批 DAQ 設定的電壓範圍。")
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
        self.voltage = []
        self.sample_rate = 1000.0
        self.total_samples = 1000
        self.fixed_voltage_range = (-10.0, 10.0)
        self.channel = ""
        self.is_simulated = None
        self.message = message
        self.update()

    def begin_capture(self, settings):
        self.clear("擷取中，等待電壓資料")
        self.sample_rate = settings["sample_rate"]
        self.total_samples = settings["samples_per_channel"]
        self.channel = settings["channel2" if self.second_channel else "channel"]
        self.fixed_voltage_range = (settings["min_voltage"], settings["max_voltage"])

    def append_progress(self, progress):
        self.voltage.extend(progress.voltage2 if self.second_channel else progress.voltage)
        self.sample_rate = progress.sample_rate
        self.total_samples = progress.total_samples
        self.channel = progress.channel2 if self.second_channel else progress.channel
        self.is_simulated = progress.is_simulated
        self.message = "擷取中（預覽）"
        self.update()

    def show_capture(self, result, message="擷取完成"):
        self.voltage = list(result.voltage2 if self.second_channel else result.voltage)
        self.sample_rate = result.sample_rate
        self.total_samples = len(self.voltage)
        self.channel = result.channel2 if self.second_channel else result.channel
        self.is_simulated = result.is_simulated
        self.fixed_voltage_range = (result.min_voltage, result.max_voltage)
        self.message = message
        self.update()

    @property
    def sample_range(self):
        return self.total_samples - 1

    @property
    def time_range(self):
        return self.sample_range / self.sample_rate

    def voltage_range(self):
        if not self.auto_scale.isChecked() or not self.voltage:
            return self.fixed_voltage_range
        low, high = min(self.voltage), max(self.voltage)
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
        for start in range(0, len(self.voltage), step):
            stop = min(start + step, len(self.voltage))
            indices = range(start, stop)
            low = min(indices, key=self.voltage.__getitem__)
            high = max(indices, key=self.voltage.__getitem__)
            for index in sorted({start, low, high, stop - 1}):
                yield index / self.sample_rate, self.voltage[index]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111111"))
        font = painter.font()
        font.setPixelSize(12)
        painter.setFont(font)
        low, high = self.voltage_range()
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
        source = "" if self.is_simulated is None else (
            " · NI 模擬裝置" if self.is_simulated else " · 實體裝置"
        )
        caption = f"{self.channel}{source}  {self.message}  {len(self.voltage)}/{self.total_samples} 筆"
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

        if self.voltage:
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
            if len(self.voltage) == 1:
                painter.drawEllipse(point, 2, 2)
            else:
                painter.drawPath(path)
            painter.restore()
        painter.end()
