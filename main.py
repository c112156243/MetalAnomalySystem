import sys
import os
import json
import random
from datetime import datetime
from queue import Empty
from daq_acquisition import CaptureWorker, AcquisitionError, apply_daq_defaults
from excel_export import save_capture_excel
from voltage_waveform import SignalWaveform
from engineering_settings import apply_engineering_defaults, validate_engineering
from engineering_dialog import EngineeringDialog
from digital_trigger import DigitalWorker
from prediction_report import PredictionPlot, SegmentResult, WINDOW_SIZE, render_report_png

from PySide6.QtCore import Qt, QTimer, QObject, QEvent
from email_notifier import (
    EmailNotifier, NotificationConfigError, apply_email_defaults, make_notification
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFileDialog,
    QTableWidgetItem
)

from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
from PySide6.QtGui import QIcon


# ============================================================
# 基本設定
# ============================================================

# 取得 main.py 所在的資料夾
BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

# 設定檔位置
CONFIG_FILE = os.path.join(
    BASE_DIR,
    "config.json"
)

# Qt Designer UI 檔案位置
UI_FILE = os.path.join(
    BASE_DIR,
    "ui",
    "main_window.ui"
)

# 視窗圖示位置
ICON_FILE = os.path.join(
    BASE_DIR,
    "app_icon.png"
)


# ============================================================
# 設定檔處理
# ============================================================

def load_config():
    """讀取 config.json"""

    default_config = apply_engineering_defaults(apply_daq_defaults(apply_email_defaults({
        "gateway1": "192.168.1.101",
        "gateway2": "192.168.1.102",
        "save_path": "data",
        "account": "user@example.com.tw",
        "device_number": "DEVICE001"
    })))

    if not os.path.exists(CONFIG_FILE):
        save_config(default_config)
        return default_config

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

        # 防止設定檔缺少欄位
        for key, value in default_config.items():
            if key not in config:
                config[key] = value

        return apply_engineering_defaults(apply_daq_defaults(apply_email_defaults(config)))

    except Exception as e:
        print("讀取設定檔失敗:", e)
        return default_config


def save_config(config):
    """儲存 config.json"""

    temporary = CONFIG_FILE + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        os.replace(temporary, CONFIG_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def show_message_box(parent, icon, title, text):
    """顯示統一樣式的訊息彈窗。"""

    message_box = QMessageBox(parent)
    message_box.setIcon(icon)
    message_box.setWindowIcon(QIcon(ICON_FILE))
    message_box.setWindowTitle(title)
    message_box.setText(text)
    message_box.setStyleSheet(
        """
        QMessageBox QLabel {
            color: #1f4e79;
            font-size: 18px;
            font-weight: bold;
        }
        QMessageBox QPushButton {
            color: white;
            background-color: #4b78c6;
            min-width: 90px;
            padding: 6px 14px;
        }
        """
    )
    message_box.exec()


# ============================================================
# 日期資料夾
# ============================================================

def create_today_folder(base_path):
    """
    建立今天的資料夾
    # 如果是相對路徑
    # 以 main.py 所在位置為基準
    例如：

    data/
    └── 2026/
        └── 08/
            └── 15/
    """
    if not os.path.isabs(base_path):

        base_path = os.path.join(
            BASE_DIR,
            base_path
        )
    today = datetime.now()

    folder = os.path.join(
        base_path,
        today.strftime("%Y"),
        today.strftime("%m"),
        today.strftime("%d")
    )

    os.makedirs(folder, exist_ok=True)

    return folder


# ============================================================
# 設定視窗
# ============================================================

class SettingsDialog(EngineeringDialog):
    def __init__(self, config, parent=None):
        super().__init__(config, parent, save_config, show_message_box)
        self.setWindowIcon(QIcon(ICON_FILE))

class MainWindow(QObject):

    def __init__(self):

        super().__init__()

        # ----------------------------------------------------
        # 讀取 UI
        # ----------------------------------------------------

        loader = QUiLoader()

        # ----------------------------------------------------
        # 確認 UI 檔案存在
        # ----------------------------------------------------

        print("UI 檔案位置：")
        print(UI_FILE)

        if not os.path.exists(UI_FILE):

            raise FileNotFoundError(
                f"找不到 UI 檔案：\n{UI_FILE}"
            )
        
        # ----------------------------------------------------
        # 開啟 UI 檔案
        # ----------------------------------------------------

        ui_file = QFile(UI_FILE)

        if not ui_file.open(QFile.ReadOnly):

            raise RuntimeError(
                f"無法開啟 UI 檔案：\n{UI_FILE}"
            )
        
        # ----------------------------------------------------
        # 載入 UI
        # ----------------------------------------------------

        self.ui = loader.load(
            ui_file
        )

        ui_file.close()

        # ----------------------------------------------------
        # 確認 UI 是否成功載入
        # ----------------------------------------------------

        if self.ui is None:

            raise RuntimeError(
                f"UI 載入失敗：\n{UI_FILE}"
            )

        # ----------------------------------------------------
        # 設定視窗標題
        # ----------------------------------------------------

        self.ui.setWindowTitle(
            "金屬製造異常警示通報系統"
        )
        self.ui.setWindowIcon(
            QIcon(ICON_FILE)
        )

        # ----------------------------------------------------
        # 讀取設定
        # ----------------------------------------------------

        self.config = load_config()

        # ----------------------------------------------------
        # 建立今天的資料夾
        # ----------------------------------------------------

        self.today_folder = create_today_folder(
            self.config["save_path"]
        )

        # ----------------------------------------------------
        # 找到 UI 元件
        # ----------------------------------------------------

        self.btnCapture = (
            self.ui.findChild(
                QPushButton,
                "btnCapture"
            )
        )

        self.btnSave = (
            self.ui.findChild(
                QPushButton,
                "btnSave"
            )
        )

        self.btnSettings = (
            self.ui.findChild(
                QPushButton,
                "btnSettings"
            )
        )
        print(
            "btnSettings =",
            self.btnSettings
        )

        self.btnExit = (
            self.ui.findChild(
                QPushButton,
                "btnExit"
            )
        )

        self.lblScore = (
            self.ui.findChild(
                QLabel,
                "lblScore"
            )
        )

        self.lblPrediction = (
            self.ui.findChild(
                QLabel,
                "lblPrediction"
            )
        )

        self.tableHistory = self.ui.tableHistory
        self.prediction_plot = PredictionPlot(self.ui.predictionFrame)
        self.ui.predictionLayout.addWidget(self.prediction_plot)
        self.voltage_plot = SignalWaveform(self.ui.voltagePlotContainer)
        self.current_plot = SignalWaveform(self.ui.currentPlotContainer, current_mode=True)
        self.signal_views = (
            (self.voltage_plot, self.ui.lblVoltageValue),
            (self.current_plot, self.ui.lblCurrentValue),
        )
        for plot, label in self.signal_views:
            plot_layout = QVBoxLayout(plot.parentWidget())
            plot_layout.setContentsMargins(0, 0, 0, 0)
            plot_layout.addWidget(plot)
            label.setToolTip(f"{plot.signal_name}最新讀值（{plot.unit}）；可用 Auto-scale chart 切換縮放。")
        self.ui.ensurePolished()
        for frame in (self.ui.gateway1Frame, self.ui.gateway2Frame, self.ui.predictionFrame):
            frame.layout().invalidate()
            frame.setMinimumHeight(max(frame.minimumHeight(), frame.minimumSizeHint().height()))

        # ----------------------------------------------------
        # 狀態 Label（已放在 .ui 內）
        # ----------------------------------------------------

        self.status_label = self.ui.findChild(
            QLabel,
            "lblStatus"
        )

        if self.status_label is None:
            raise RuntimeError("UI 中找不到 lblStatus")
        self.status_label.setWordWrap(True)

        # 獨立使用既有 QStatusBar，不覆蓋擷取／儲存狀態。
        self.email_status_label = QLabel(self.ui)
        self.email_status_label.setObjectName("lblEmailStatus")
        self.email_status_label.setStyleSheet("color: #222222; padding: 3px; font-size: 16px;")
        self.email_status_label.setWordWrap(True)
        self.ui.statusBar().addWidget(self.email_status_label, 1)
        self.notifier = EmailNotifier()
        self._capture_worker = None
        self._digital_worker = None
        self._digital_ready = False
        self._digital_pending = False
        self._settings_open = False
        self._auto_save = False
        self._stopping = False
        self._saving = False
        self._preview_count = 0
        self._segments = []
        self.current_segments = ()
        self._closing = False
        self._capture_id = 0
        self._latest_notification_id = None
        self._notification_items = {}
        self._notification_times = {}
        self.ui.installEventFilter(self)
        self._email_timer = QTimer(self)
        self._email_timer.timeout.connect(self.poll_email_results)
        self._email_timer.start(100)
        self._capture_timer = QTimer(self)
        self._capture_timer.setInterval(50)
        self._capture_timer.timeout.connect(self.poll_capture_results)
        self._digital_timer = QTimer(self)
        self._digital_timer.timeout.connect(self.poll_digital)
        self._digital_timer.start(20)
        self.show_email_ready_status()

        # ----------------------------------------------------
        # 初始化資料
        # ----------------------------------------------------

        self.current_voltage = []
        self.current_current = []

        self.current_score = None
        self.current_prediction = None

        self.current_capture = None
        self.last_excel_path = None
        self.last_png_path = None

        # ----------------------------------------------------
        # 初始化 Table
        # ----------------------------------------------------

        self.setup_history_table()

        # ----------------------------------------------------
        # 按鈕事件
        # ----------------------------------------------------

        self.btnCapture.clicked.connect(
            self.capture_data
        )

        self.btnSave.clicked.connect(
            self.save_data
        )

        self.btnSettings.clicked.connect(
            self.open_settings
        )

        self.btnExit.clicked.connect(
            self.ui.close
        )

        # ----------------------------------------------------
        # 初始顯示
        # ----------------------------------------------------

        self.lblScore.setText(
            "分數：--"
        )

        self.lblPrediction.setText(
            "預測結果：等待擷取"
        )
        self.lblPrediction.setToolTip("OK／NG 仍為隨機測試判定，尚未串接 AI 模型；NG 依設定寄信。")

        self.update_gateway_display()

        self.status_label.setText(
            "系統待機中"
        )
        # 依實際字型與波形高度保留最小空間，避免縮小視窗時圖表被下方區塊遮住。
        self.ui.setMinimumSize(self.ui.minimumSize().expandedTo(self.ui.minimumSizeHint()))
        self.configure_digital()

    # ========================================================
    # 歷史紀錄 Table
    # ========================================================

    def setup_history_table(self):

        self.tableHistory.setColumnCount(3)

        self.tableHistory.setHorizontalHeaderLabels(
            [
                "時間",
                "分數",
                "預測結果"
            ]
        )

        self.tableHistory.setRowCount(0)

        self.tableHistory.setEditTriggers(
            self.tableHistory.EditTrigger.NoEditTriggers
        )

        self.tableHistory.horizontalHeader().setStretchLastSection(
            True
        )
        header = self.tableHistory.horizontalHeader()
        header.setSectionResizeMode(header.ResizeMode.Stretch)

    # ========================================================
    # 顯示閘道資訊
    # ========================================================

    def update_gateway_display(self):

        gateway1 = self.config["daq"]["channel"]
        gateway2 = "程式模擬（非實測）"

        self.ui.lblGateway1.setText(
            gateway1
        )

        self.ui.lblGateway2.setText(
            gateway2
        )

    # ========================================================
    # 按鈕執行中樣式
    # ========================================================

    def set_action_button_running(self, button, running):

        if running:
            button.setStyleSheet(
                """
                QPushButton {
                    background-color: #72B447;
                    color: white;
                    border: none;
                    font-size: 20px;
                    font-weight: bold;
                    padding: 4px 14px;
                    min-height: 48px;
                }
                """
            )
        else:
            # 清除 inline style，恢復 .ui 裡的共用藍色樣式
            button.setStyleSheet("")

    # ========================================================
    # 擷取資料
    # ========================================================

    def capture_data(self, checked=False, external=False):

        if self._closing or self._capture_worker is not None or self._saving or self._settings_open:
            return
        try:
            engineering, _ = validate_engineering(self.config)
            if engineering["trigger_mode"] and not external:
                self.status_label.setText("目前為外部模式，請操作外接按鈕；可在工程設定切換內部模式。")
                return
            if external and not self._digital_ready:
                return
            if engineering["do_channel"] and not self._digital_ready:
                raise AcquisitionError("數位輸出尚未就緒，請確認工程設定與設備。")
            worker = CaptureWorker(self.config.get("daq", {}), continuous=external)
        except AcquisitionError as error:
            self.capture_failed(str(error))
            return
        self._auto_save = external
        self._stopping = False
        self._preview_count = 0
        self._segments = []
        self.prediction_plot.show_segments(())
        self._latest_notification_id = None
        self.email_status_label.setText("Email：擷取中，等待本次結果（先前通知狀態請查看歷史列提示）")
        self.status_label.setText(
            f"進行中：正在擷取 {worker.settings['channel']} 電壓，並產生程式模擬電流..."
        )

        # ----------------------------------------------------
        # 進行中狀態變色
        # ----------------------------------------------------

        self.status_label.setStyleSheet(
            "background-color: yellow; "
            "color: black; "
            "font-weight: bold;"
        )

        self.set_action_button_running(
            self.btnCapture,
            True
        )

        self.btnCapture.setEnabled(False)
        self.btnSave.setEnabled(False)
        self.btnSettings.setEnabled(False)

        # ----------------------------------------------------
        # 背景執行緒操作 DAQ；Timer 僅接收結果並更新 UI。
        # ----------------------------------------------------

        self._capture_worker = worker
        for plot, label in self.signal_views:
            plot.begin_capture(worker.settings)
            label.setText(f"-- {plot.unit}")
        try:
            worker.start()
        except Exception:
            self._capture_worker = None
            self.capture_failed("無法啟動擷取工作，請重試。")
            return
        self._capture_timer.start()

    def poll_capture_results(self):
        worker = self._capture_worker
        if worker is None:
            return
        while True:
            try:
                progress = worker.progress.get_nowait()
            except Empty:
                break
            if not self._closing:
                for plot, label in self.signal_views:
                    plot.append_progress(progress)
                    label.setText(f"{plot.values[-1]:.4f} {plot.unit}")
                self._preview_count += len(progress.voltage)
                self.classify_segments(self._preview_count)
        if worker.is_running():
            return
        worker.wait()
        result, error = worker.results.get_nowait()
        if worker.cancel.is_set():
            result, error = None, error or "本次擷取已取消，資料未採用。"
        self._capture_worker = None
        self._capture_timer.stop()
        if self._closing:
            return
        if error:
            self.capture_failed(error)
        elif result is not None:
            self.complete_capture(result)
        else:
            self.capture_failed("本次擷取已取消，資料未採用。")

    def classify_segments(self, count):
        changed = False
        while len(self._segments) < count // WINDOW_SIZE:
            score, prediction = self.predict()
            start = len(self._segments) * WINDOW_SIZE
            self._segments.append(SegmentResult(start, start + WINDOW_SIZE, score, prediction))
            changed = True
            reset_on_stop = self._stopping and self.config["engineering"]["trigger_mode"] == 1
            if prediction == "NG" and self._digital_worker is not None and not reset_on_stop:
                self._digital_worker.alarm.set()
        if changed:
            self.prediction_plot.show_segments(self._segments)

    def configure_digital(self):
        self._digital_ready = False
        self._digital_pending = True
        if self._digital_worker is not None:
            self._digital_worker.shutdown()

    def poll_digital(self):
        worker = self._digital_worker
        if worker is not None:
            while True:
                try:
                    event, detail = worker.events.get_nowait()
                except Empty:
                    break
                if self._closing or self._digital_pending or self._settings_open:
                    continue
                if event == "ready":
                    self._digital_ready = True
                    self.status_label.setText("數位 I/O 就緒；外部模式請先放開按鈕，再按下開始。")
                elif event == "error":
                    self._digital_ready = False
                    if self._capture_worker is not None:
                        self._capture_worker.shutdown()
                    self._auto_save = False
                    self.status_label.setText(detail + " 可開啟工程設定重新啟用。")
                    show_message_box(self.ui, QMessageBox.Icon.Warning, "數位 I/O 錯誤", detail)
                elif not self._saving:
                    self.handle_external_event(event)
            if not worker.is_running():
                worker.wait()
                self._digital_worker = None
                self._digital_ready = False
        if (self._digital_pending and self._digital_worker is None
                and not self._closing and not self._settings_open):
            self._digital_pending = False
            try:
                settings, lines = validate_engineering(self.config)
                if settings["trigger_mode"] or settings["do_channel"]:
                    self._digital_worker = DigitalWorker(settings, lines)
                    self._digital_worker.start()
            except (AcquisitionError, RuntimeError) as error:
                self._digital_worker = None
                self.status_label.setText(f"工程設定待確認：{error}")

    def handle_external_event(self, event):
        if self._closing or self._settings_open or self._saving or not self._digital_ready:
            return
        mode = self.config["engineering"]["trigger_mode"]
        if event == "pressed":
            if self._digital_worker is not None:
                self._digital_worker.alarm.clear()
            if mode == 0:
                return
            if self._capture_worker is None:
                self.capture_data(external=True)
            elif mode == 1:
                self.stop_external_capture()
        elif event == "released" and mode == 2:
            self.stop_external_capture()

    def stop_external_capture(self):
        if self._capture_worker is not None and self._auto_save and not self._stopping:
            self._stopping = True
            self._capture_worker.finish()
            self.status_label.setText("已收到停止要求，正在整理資料並儲存 Excel 與 PNG...")

    def capture_failed(self, reason):
        self._auto_save = False
        self._stopping = False
        self._segments = []
        self._preview_count = 0
        self.prediction_plot.show_segments(self.current_segments)
        for plot, label in self.signal_views:
            if self.current_capture is not None:
                plot.show_capture(self.current_capture, "擷取失敗，保留上一批")
                label.setText(f"{plot.values[-1]:.4f} {plot.unit}")
            else:
                plot.clear("擷取失敗，尚無成功資料")
                label.setText(f"-- {plot.unit}")
        self._latest_notification_id = None
        previous = "；保留上一批成功資料" if self.current_voltage else ""
        self.status_label.setText(f"擷取失敗：{reason}{previous}")
        self.status_label.setStyleSheet("color: #a00000;")
        self.email_status_label.setText("Email：本次擷取失敗，不產生新通知")
        self.btnCapture.setEnabled(True)
        self.btnSave.setEnabled(True)
        self.btnSettings.setEnabled(True)
        self.set_action_button_running(self.btnCapture, False)
        if "未足1024筆" in reason and not self._closing:
            show_message_box(self.ui, QMessageBox.Icon.Warning, "資料不足", reason)

    def complete_capture(self, result):

        if self._closing:
            return
        if len(result.voltage) < WINDOW_SIZE:
            self.capture_failed(f"資料未足1024筆（本次 {len(result.voltage)} 筆），不判定、不儲存。")
            return
        if len(result.voltage) != len(result.current):
            self.capture_failed("電壓與模擬電流筆數不一致。")
            return
        self.classify_segments(len(result.voltage))
        self.current_segments = tuple(self._segments)
        self._segments = []
        self._preview_count = 0
        self.current_capture = result
        self.current_voltage = list(result.voltage)
        self.current_current = list(result.current)
        for plot, label in self.signal_views:
            plot.show_capture(result)
            label.setText(f"{plot.values[-1]:.4f} {plot.unit}")

        # ----------------------------------------------------
        # 進行預測
        # ----------------------------------------------------

        score = min(item.score for item in self.current_segments)
        prediction = "NG" if any(item.prediction == "NG" for item in self.current_segments) else "OK"

        self.current_score = score
        self.current_prediction = prediction
        completed_at = result.completed_at

        # ----------------------------------------------------
        # 更新畫面
        # ----------------------------------------------------

        self.lblScore.setText(
            f"分數：{score:.2f}"
        )

        self.lblPrediction.setText(
            f"模擬判定：{prediction}（{len(self.current_segments)} 段）"
        )

        # ----------------------------------------------------
        # 顯示結果
        # ----------------------------------------------------

        if prediction == "OK":

            self.lblPrediction.setStyleSheet(
                """
                QLabel {
                    background-color: #90EE90;
                    color: black;
                    font-size: 20px;
                    font-weight: bold;
                    padding: 10px;
                }
                """
            )

        else:

            self.lblPrediction.setStyleSheet(
                """
                QLabel {
                    background-color: #FF7F7F;
                    color: black;
                    font-size: 20px;
                    font-weight: bold;
                    padding: 10px;
                }
                """
            )

        # ----------------------------------------------------
        # 完成擷取
        # ----------------------------------------------------

        self.status_label.setText(
            f"擷取完成：{result.channel} 電壓，{len(result.voltage)} 筆，"
            f"{'NI 模擬裝置' if result.is_simulated else '實體裝置'}；電流為程式模擬，OK／NG 為隨機測試"
        )

        self.status_label.setStyleSheet(
            ""
        )

        self.btnCapture.setEnabled(True)
        self.btnSave.setEnabled(True)
        self.btnSettings.setEnabled(True)

        self.set_action_button_running(
            self.btnCapture,
            False
        )

        # ----------------------------------------------------
        # 新增歷史紀錄
        # ----------------------------------------------------

        self.add_history()
        self.notify_capture_completed(completed_at, score, prediction)
        auto_save = self._auto_save
        self._auto_save = False
        self._stopping = False
        if auto_save:
            self.save_data(automatic=True)

    def show_email_ready_status(self):
        email = self.config.get("email", {})
        if isinstance(email, dict) and email.get("enabled", False) is False:
            status = "通知未啟用"
        else:
            try:
                make_notification(self.config, 0, datetime.now(), 0, "NG")
                status = "通知已啟用，等待 NG 擷取結果"
            except NotificationConfigError as error:
                status = "設定錯誤：" + str(error)
        self.email_status_label.setText("Email：" + status)

    def notify_capture_completed(self, completed_at, score, prediction):
        self._capture_id += 1
        capture_id = self._capture_id
        self._latest_notification_id = capture_id
        self._notification_times[capture_id] = completed_at
        self._notification_items[capture_id] = self.tableHistory.item(
            self.tableHistory.rowCount() - 1, 2
        )
        try:
            job = make_notification(self.config, capture_id, completed_at, score, prediction)
            if prediction != "NG":
                status = "本次 OK，不寄送通知"
            elif job is None:
                status = "通知未啟用"
            else:
                error = self.notifier.submit(job)
                status = "寄送失敗：" + error if error else "通知等待寄送"
        except NotificationConfigError as error:
            status = "設定錯誤：" + str(error)
        self.update_email_status(capture_id, status)

    def update_email_status(self, capture_id, status):
        completed_at = self._notification_times[capture_id]
        text = f"Email #{capture_id}（{completed_at:%Y-%m-%d %H:%M:%S}）：{status}"
        item = self._notification_items.get(capture_id)
        if item is not None:
            item.setToolTip(text)
        if capture_id == self._latest_notification_id and not self._closing:
            self.email_status_label.setText(text)

    def poll_email_results(self):
        while True:
            try:
                capture_id, status = self.notifier.results.get_nowait()
            except Empty:
                break
            self.update_email_status(capture_id, status)
        if (self._closing and not self.notifier.is_running()
                and self._capture_worker is None and self._digital_worker is None):
            self.notifier.wait()
            self.ui.close()

    # ========================================================
    # 預測
    # ========================================================

    def predict(self):

        """
        目前先使用模擬模型。

        未來這裡改成：

        Voltage + Current
                ↓
            preprocessing
                ↓
             1DCNN
                ↓
             probability
                ↓
              OK / NG
        """

        score = random.uniform(
            0.0,
            1.0
        )

        if score >= 0.5:

            prediction = "OK"

        else:

            prediction = "NG"

        return score, prediction

    # ========================================================
    # 歷史紀錄
    # ========================================================

    def add_history(self):

        row = (
            self.tableHistory.rowCount()
        )

        self.tableHistory.insertRow(
            row
        )

        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        time_item = QTableWidgetItem(
            timestamp
        )

        score_item = QTableWidgetItem(
            f"{self.current_score:.2f}"
        )

        prediction_item = QTableWidgetItem(
            self.current_prediction
        )

        self.tableHistory.setItem(
            row,
            0,
            time_item
        )

        self.tableHistory.setItem(
            row,
            1,
            score_item
        )

        self.tableHistory.setItem(
            row,
            2,
            prediction_item
        )

        # ----------------------------------------------------
        # NG 顯示醒目
        # ----------------------------------------------------

        if self.current_prediction == "NG":

            prediction_item.setTextAlignment(
                Qt.AlignCenter
            )

    # ========================================================
    # 儲存 Excel
    # ========================================================

    def save_data(self, checked=False, automatic=False):
        if self._closing or self._capture_worker is not None or self._saving:
            return
        if self.current_capture is None:
            show_message_box(
                self.ui, QMessageBox.Icon.Warning, "無資料",
                "目前沒有可儲存的擷取資料。\n請先按「擷取」。"
            )
            return

        self.set_action_button_running(self.btnSave, True)
        self._saving = True
        self.btnSave.setEnabled(False)
        self.btnCapture.setEnabled(False)
        self.btnSettings.setEnabled(False)
        self.status_label.setText("進行中：正在儲存 Excel 與 PNG...")
        self.status_label.setStyleSheet("")
        try:
            self.today_folder = create_today_folder(self.config["save_path"])
            filepath = save_capture_excel(
                self.today_folder, self.current_capture,
                self.current_score, self.current_prediction, datetime.now(),
                segments=self.current_segments,
                report_png=render_report_png(self.current_capture, self.current_segments),
            )
            self.last_excel_path = filepath
            self.last_png_path = os.path.splitext(filepath)[0] + ".png"
            self.status_label.setText(f"Excel 與 PNG 儲存完成：{os.path.basename(filepath)}")
            if not automatic:
                show_message_box(
                    self.ui, QMessageBox.Icon.Information, "儲存成功",
                    f"資料已儲存：\n\n{filepath}\n{self.last_png_path}"
                )
        except Exception as error:
            self.status_label.setText("Excel／PNG 儲存失敗，擷取資料仍保留，可重新儲存")
            show_message_box(
                self.ui, QMessageBox.Icon.Critical, "儲存失敗",
                f"Excel／PNG 儲存失敗：\n{error}"
            )
        finally:
            # 儲存期間的按鍵不排成下一次擷取，避免儲存完後突然啟動。
            if self._digital_worker is not None:
                retained = []
                while True:
                    try:
                        item = self._digital_worker.events.get_nowait()
                    except Empty:
                        break
                    if item[0] not in ("pressed", "released"):
                        retained.append(item)
                for item in retained:
                    self._digital_worker.events.put(item)
            self._saving = False
            for button in (self.btnSave, self.btnCapture, self.btnSettings):
                button.setEnabled(not self._closing)
            self.set_action_button_running(self.btnSave, False)

    # ========================================================
    # 工程設定
    # ========================================================

    def open_settings(self):

        if self._closing or self._capture_worker is not None or self._saving:
            return
        self._settings_open = True
        self.configure_digital()

        try:

            dialog = SettingsDialog(
                self.config,
                self.ui
            )

            print("DEBUG: SettingsDialog 建立成功")

            result = dialog.exec()

            print(
                f"DEBUG: SettingsDialog 結束，result = {result}"
        )

            if result:

                self.config = load_config()

                self.update_gateway_display()

                self.today_folder = create_today_folder(
                    self.config["save_path"]
                )

                self.status_label.setText(
                    "設定已更新"
                )
                if self._latest_notification_id is None:
                    self.show_email_ready_status()

        except Exception as e:

            print(
                "工程設定發生錯誤：",
                repr(e)
            )

            show_message_box(
                self.ui,
                QMessageBox.Icon.Critical,
                "工程設定錯誤",
                f"開啟工程設定時發生錯誤：\n\n{e}"
            )
        finally:
            self._settings_open = False
            self.configure_digital()

    # ========================================================
    # 關閉程式
    # ========================================================

    def eventFilter(self, watched, event):
        # QUiLoader 顯示的是 self.ui，必須攔截該物件的關閉事件。
        if watched is self.ui and event.type() == QEvent.Close:
            self._closing = True
            if self._capture_worker is not None:
                self._capture_worker.shutdown()
            if self._digital_worker is not None:
                self._digital_worker.shutdown()
            self.notifier.shutdown()
            if (self.notifier.is_running() or self._capture_worker is not None
                    or self._digital_worker is not None):
                event.ignore()
                self.btnCapture.setEnabled(False)
                self.btnSave.setEnabled(False)
                self.btnSettings.setEnabled(False)
                self.email_status_label.setText(
                    "Email：正在關閉，等待目前寄送結束；尚未開始的通知已取消"
                )
                self.status_label.setText("正在關閉，等待擷取工作釋放裝置...")
                return True
            self.notifier.wait()
            self._email_timer.stop()
            self._digital_timer.stop()
        return super().eventFilter(watched, event)


# ============================================================
# 主程式
# ============================================================

def main():

    app = QApplication(
        sys.argv
    )

    window = MainWindow()

    window.ui.show()

    try:
        exit_code = app.exec()
    finally:
        # 保護非視窗關閉路徑（例如 QApplication.quit）。
        window.notifier.shutdown()
        if window._digital_worker is not None:
            window._digital_worker.shutdown()
            window._digital_worker.wait()
        if window._capture_worker is not None:
            window._capture_worker.shutdown()
            window._capture_worker.wait()
        window.notifier.wait()
    sys.exit(exit_code)


if __name__ == "__main__":

    main()
