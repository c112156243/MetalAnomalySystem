import sys
import os
import csv
import json
import random
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
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


# ============================================================
# 設定檔處理
# ============================================================

def load_config():
    """讀取 config.json"""

    default_config = {
        "gateway1": "192.168.1.101",
        "gateway2": "192.168.1.102",
        "save_path": "data",
        "account": "user@example.com.tw",
        "device_number": "DEVICE001"
    }

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

        return config

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
        self.resize(450, 300)

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

        QMessageBox.information(
            self,
            "設定完成",
            "設定已成功儲存。"
        )

        self.accept()


# ============================================================
# 主視窗
# ============================================================

class MainWindow:

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
        # 新增狀態 Label
        # ----------------------------------------------------

        self.status_label = QLabel(
            "系統待機中"
        )

        self.status_label.setAlignment(
            Qt.AlignCenter
        )


        # ----------------------------------------------------
        # 初始化資料
        # ----------------------------------------------------

        self.current_voltage = []
        self.current_current = []

        self.current_score = None
        self.current_prediction = None

        self.last_csv_path = None

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

        self.update_gateway_display()

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
            f"閘道位置1：{gateway1}"
        )

        self.ui.lblGateway2.setText(
            f"閘道位置2：{gateway2}"
        )

    # ========================================================
    # 擷取資料
    # ========================================================

    def capture_data(self):

        self.status_label.setText(
            "進行中：正在擷取 Voltage / Current..."
        )

        # ----------------------------------------------------
        # 進行中狀態變色
        # ----------------------------------------------------

        self.status_label.setStyleSheet(
            "background-color: yellow; "
            "color: black; "
            "font-weight: bold;"
        )

        self.btnCapture.setEnabled(False)

        # ----------------------------------------------------
        # 使用 Timer 模擬設備擷取
        # ----------------------------------------------------

        QTimer.singleShot(
            1000,
            self.generate_test_data
        )

    # ========================================================
    # 產生測試資料
    # ========================================================

    def generate_test_data(self):

        # ----------------------------------------------------
        # 模擬 1000 筆 Voltage
        # ----------------------------------------------------

        self.current_voltage = [
            random.uniform(4.8, 5.2)
            for _ in range(1000)
        ]

        # ----------------------------------------------------
        # 模擬 1000 筆 Current
        # ----------------------------------------------------

        self.current_current = [
            random.uniform(0.8, 1.2)
            for _ in range(1000)
        ]

        # ----------------------------------------------------
        # 進行預測
        # ----------------------------------------------------

        score, prediction = (
            self.predict()
        )

        self.current_score = score
        self.current_prediction = prediction

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
            "擷取完成"
        )

        self.status_label.setStyleSheet(
            ""
        )

        self.btnCapture.setEnabled(True)

        # ----------------------------------------------------
        # 新增歷史紀錄
        # ----------------------------------------------------

        self.add_history()

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
    # 儲存 CSV
    # ========================================================

    def save_data(self):

        if not self.current_voltage:

            QMessageBox.warning(
                self,
                "無資料",
                "目前沒有可儲存的擷取資料。\n"
                "請先按「擷取」。"
            )

            return

        # ----------------------------------------------------
        # 確認今天資料夾
        # ----------------------------------------------------

        self.today_folder = create_today_folder(
            self.config["save_path"]
        )

        # ----------------------------------------------------
        # CSV 檔名
        # ----------------------------------------------------

        now = datetime.now()

        filename = (
            now.strftime(
                "%Y%m%d_%H%M%S"
            )
            + "_001.csv"
        )

        filepath = os.path.join(
            self.today_folder,
            filename
        )

        # ----------------------------------------------------
        # 寫入 CSV
        # ----------------------------------------------------

        try:

            with open(
                filepath,
                "w",
                newline="",
                encoding="utf-8-sig"
            ) as f:

                writer = csv.writer(f)

                # Header
                writer.writerow(
                    [
                        "Timestamp",
                        "Voltage",
                        "Current",
                        "Score",
                        "Prediction"
                    ]
                )

                timestamp = now.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                for voltage, current in zip(
                    self.current_voltage,
                    self.current_current
                ):

                    writer.writerow(
                        [
                            timestamp,
                            voltage,
                            current,
                            self.current_score,
                            self.current_prediction
                        ]
                    )

            self.last_csv_path = filepath

            self.status_label.setText(
                "資料儲存完成"
            )

            QMessageBox.information(
                self,
                "儲存成功",
                f"資料已儲存：\n\n{filepath}"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "儲存失敗",
                f"CSV 儲存失敗：\n{e}"
            )

    # ========================================================
    # 帳號設定
    # ========================================================

    def open_settings(self):

        dialog = SettingsDialog(
            self.config,
            self
        )

        if dialog.exec():

            self.config = load_config()

            self.update_gateway_display()

            self.today_folder = (
                create_today_folder(
                    self.config["save_path"]
                )
            )

            self.status_label.setText(
                "設定已更新"
            )

    # ========================================================
    # 關閉程式
    # ========================================================

    def closeEvent(self, event):

        reply = QMessageBox.question(
            self,
            "確認離開",
            "確定要離開系統嗎？",
            QMessageBox.Yes |
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:

            event.accept()

        else:

            event.ignore()


# ============================================================
# 主程式
# ============================================================

def main():

    app = QApplication(
        sys.argv
    )

    window = MainWindow()

    window.ui.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":

    main()