import sys
import os
import json
import random
from datetime import datetime
from queue import Empty
from daq_acquisition import CaptureWorker, AcquisitionError, apply_daq_defaults
from excel_export import save_capture_excel

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

    default_config = apply_daq_defaults(apply_email_defaults({
        "gateway1": "192.168.1.101",
        "gateway2": "192.168.1.102",
        "save_path": "data",
        "account": "user@example.com.tw",
        "device_number": "DEVICE001"
    }))

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

        return apply_daq_defaults(apply_email_defaults(config))

    except Exception as e:
        print("讀取設定檔失敗:", e)
        return default_config


def save_config(config):
    """儲存 config.json"""

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            config,
            f,
            ensure_ascii=False,
            indent=4
        )


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

class SettingsDialog(QDialog):

    def __init__(self, config, parent=None):

        super().__init__(parent)

        self.config = config

        self.setWindowTitle("帳號設定")
        self.setWindowIcon(QIcon(ICON_FILE))
        self.resize(450, 300)
        self.setStyleSheet(
            """
            QDialog {
                background-color: white;
            }
            QDialog QLabel {
                color: #1f4e79;
                font-size: 16px;
                font-weight: bold;
            }
            QDialog QLineEdit {
                color: #1f4e79;
                background-color: white;
                border: 1px solid #8aa9c7;
                padding: 5px;
            }
            QDialog QPushButton {
                color: white;
                background-color: #4b78c6;
                min-height: 36px;
                padding: 4px 14px;
            }
            """
        )

        # ----------------------------------------------------
        # 欄位
        # ----------------------------------------------------

        self.gateway1_edit = QLineEdit(
            config["gateway1"]
        )

        self.gateway2_edit = QLineEdit(
            config["gateway2"]
        )

        self.path_edit = QLineEdit(
            config["save_path"]
        )

        self.account_edit = QLineEdit(
            config["account"]
        )

        self.device_edit = QLineEdit(
            config["device_number"]
        )

        # ----------------------------------------------------
        # 選擇路徑按鈕
        # ----------------------------------------------------

        self.btnBrowse = QPushButton("變更路徑")

        self.btnBrowse.clicked.connect(
            self.select_folder
        )

        path_layout = QHBoxLayout()

        path_layout.addWidget(
            self.path_edit
        )

        path_layout.addWidget(
            self.btnBrowse
        )

        # ----------------------------------------------------
        # Form
        # ----------------------------------------------------

        form = QFormLayout()

        form.addRow(
            "閘道位置1:",
            self.gateway1_edit
        )

        form.addRow(
            "閘道位置2:",
            self.gateway2_edit
        )

        form.addRow(
            "儲存路徑:",
            path_layout
        )

        form.addRow(
            "帳號:",
            self.account_edit
        )

        form.addRow(
            "裝置號碼:",
            self.device_edit
        )

        # ----------------------------------------------------
        # 按鈕
        # ----------------------------------------------------

        self.btnSave = QPushButton("儲存變更")
        self.btnCancel = QPushButton("取消")

        self.btnSave.clicked.connect(
            self.save_settings
        )

        self.btnCancel.clicked.connect(
            self.reject
        )

        button_layout = QHBoxLayout()

        button_layout.addWidget(
            self.btnSave
        )

        button_layout.addWidget(
            self.btnCancel
        )

        # ----------------------------------------------------
        # 主 Layout
        # ----------------------------------------------------

        layout = QVBoxLayout()

        layout.addLayout(form)

        layout.addStretch()

        layout.addLayout(button_layout)

        self.setLayout(layout)

    # --------------------------------------------------------
    # 選擇資料夾
    # --------------------------------------------------------

    def select_folder(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "選擇儲存資料夾"
        )

        if folder:
            self.path_edit.setText(folder)

    # --------------------------------------------------------
    # 儲存設定
    # --------------------------------------------------------

    def save_settings(self):

        self.config["gateway1"] = (
            self.gateway1_edit.text()
        )

        self.config["gateway2"] = (
            self.gateway2_edit.text()
        )

        self.config["save_path"] = (
            self.path_edit.text()
        )

        self.config["account"] = (
            self.account_edit.text()
        )

        self.config["device_number"] = (
            self.device_edit.text()
        )

        save_config(self.config)

        show_message_box(
            self,
            QMessageBox.Icon.Information,
            "設定完成",
            "設定已成功儲存。"
        )

        self.accept()


# ============================================================
# 主視窗
# ============================================================

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
        self.email_status_label.setStyleSheet("color: #222222; padding: 3px;")
        self.email_status_label.setWordWrap(True)
        self.ui.statusBar().addWidget(self.email_status_label, 1)
        self.notifier = EmailNotifier()
        self._capture_worker = None
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

    # ========================================================
    # 顯示閘道資訊
    # ========================================================

    def update_gateway_display(self):

        gateway1 = self.config["gateway1"]
        gateway2 = self.config["gateway2"]

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

    def capture_data(self):

        if self._closing or self._capture_worker is not None:
            return
        try:
            worker = CaptureWorker(self.config.get("daq", {}))
        except AcquisitionError as error:
            self.capture_failed(str(error))
            return
        self._latest_notification_id = None
        self.email_status_label.setText("Email：擷取中，等待本次結果（先前通知狀態請查看歷史列提示）")
        self.status_label.setText(
            f"進行中：正在擷取 {worker.settings['channel']} 電壓..."
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
        try:
            worker.start()
        except Exception:
            self._capture_worker = None
            self.capture_failed("無法啟動擷取工作，請重試。")
            return
        self._capture_timer.start()

    def poll_capture_results(self):
        worker = self._capture_worker
        if worker is None or worker.is_running():
            return
        worker.wait()
        result, error = worker.results.get_nowait()
        self._capture_worker = None
        self._capture_timer.stop()
        if self._closing:
            return
        if error:
            self.capture_failed(error)
        elif result is not None:
            self.complete_capture(result)

    def capture_failed(self, reason):
        self._latest_notification_id = None
        previous = "；保留上一批成功資料" if self.current_voltage else ""
        self.status_label.setText(f"擷取失敗：{reason}{previous}")
        self.status_label.setStyleSheet("color: #a00000;")
        self.email_status_label.setText("Email：本次擷取失敗，不產生新通知")
        self.btnCapture.setEnabled(True)
        self.btnSave.setEnabled(True)
        self.btnSettings.setEnabled(True)
        self.set_action_button_running(self.btnCapture, False)

    def complete_capture(self, result):

        if self._closing:
            return
        self.current_capture = result
        self.current_voltage = list(result.voltage)
        self.current_current = [None] * len(result.voltage)

        # ----------------------------------------------------
        # 進行預測
        # ----------------------------------------------------

        score, prediction = (
            self.predict()
        )

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
            f"預測結果：{prediction}"
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
            f"擷取完成：{result.channel}，{len(result.voltage)} 筆，"
            f"{'NI 模擬裝置' if result.is_simulated else '實體裝置'}；電流未量測，OK／NG 為隨機測試"
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
                and self._capture_worker is None):
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

    def save_data(self):
        if self._closing or self._capture_worker is not None:
            return
        if self.current_capture is None:
            show_message_box(
                self.ui, QMessageBox.Icon.Warning, "無資料",
                "目前沒有可儲存的擷取資料。\n請先按「擷取」。"
            )
            return

        self.set_action_button_running(self.btnSave, True)
        self.btnSave.setEnabled(False)
        self.status_label.setText("進行中：正在儲存 Excel...")
        self.status_label.setStyleSheet("")
        try:
            self.today_folder = create_today_folder(self.config["save_path"])
            filepath = save_capture_excel(
                self.today_folder, self.current_capture,
                self.current_score, self.current_prediction, datetime.now(),
            )
            self.last_excel_path = filepath
            self.status_label.setText("Excel 資料儲存完成")
            show_message_box(
                self.ui, QMessageBox.Icon.Information, "儲存成功",
                f"資料已儲存：\n\n{filepath}"
            )
        except Exception as error:
            self.status_label.setText("Excel 儲存失敗，擷取資料仍保留，可重新儲存")
            show_message_box(
                self.ui, QMessageBox.Icon.Critical, "儲存失敗",
                f"Excel 儲存失敗：\n{error}"
            )
        finally:
            self.btnSave.setEnabled(not self._closing)
            self.set_action_button_running(self.btnSave, False)

    # ========================================================
    # 帳號設定
    # ========================================================

    def open_settings(self):

        print("DEBUG: 帳號設定按鈕被按下")

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
                "帳號設定發生錯誤：",
                repr(e)
            )

            show_message_box(
                self.ui,
                QMessageBox.Icon.Critical,
                "帳號設定錯誤",
                f"開啟帳號設定時發生錯誤：\n\n{e}"
            )

    # ========================================================
    # 關閉程式
    # ========================================================

    def eventFilter(self, watched, event):
        # QUiLoader 顯示的是 self.ui，必須攔截該物件的關閉事件。
        if watched is self.ui and event.type() == QEvent.Close:
            self._closing = True
            if self._capture_worker is not None:
                self._capture_worker.shutdown()
            self.notifier.shutdown()
            if self.notifier.is_running() or self._capture_worker is not None:
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
        if window._capture_worker is not None:
            window._capture_worker.shutdown()
            window._capture_worker.wait()
        window.notifier.wait()
    sys.exit(exit_code)


if __name__ == "__main__":

    main()
