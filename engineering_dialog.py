"""工程設定視窗；只有驗證及寫檔成功後才更新使用中的設定。"""

from copy import deepcopy
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)
from daq_acquisition import AcquisitionError, apply_daq_defaults
from engineering_settings import apply_engineering_defaults, validate_engineering


class EngineeringDialog(QDialog):
    def __init__(self, config, parent, save_callback, message_callback):
        super().__init__(parent)
        self.config = config
        self.save_callback = save_callback
        self.message_callback = message_callback
        snapshot = apply_engineering_defaults(apply_daq_defaults(config))
        daq = snapshot["daq"]
        engineering = snapshot["engineering"]
        self.setWindowTitle("工程設定")
        self.resize(680, 720)
        self.setStyleSheet("QDialog { background: white; } QLabel { color: #1f4e79; font-size: 16px; }"
                          "QLineEdit, QComboBox { color: #222; background: white; font-size: 16px; padding: 4px; }"
                          "QComboBox QAbstractItemView { color: #222; background-color: white;"
                          " selection-color: white; selection-background-color: #4b78c6; }"
                          "QComboBox QAbstractItemView::item { color: #222; background-color: white; }"
                          "QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover"
                          " { color: white; background-color: #4b78c6; }"
                          "QPushButton { color: white; background: #4b78c6; padding: 8px; font-size: 16px; }")
        self.device_edit = QLineEdit(config["device_number"])
        self.daq_device_edit = QLineEdit(daq["channel"].split("/")[0])
        self.gateway1_edit = QLineEdit("/" + daq["channel"].split("/", 1)[1])
        self.gateway2_edit = QLineEdit("/ai1（預留，目前電流為程式模擬）")
        self.gateway2_edit.setEnabled(False)
        self.di_edit = QLineEdit(engineering["di_channel"].split("/", 1)[-1])
        self.do_edit = QLineEdit(engineering["do_channel"].split("/", 1)[-1])
        self.do_edit.setPlaceholderText("空白停用；例如 port1/line0")
        self.count_edit = QLineEdit(str(daq["samples_per_channel"]))
        self.rate_edit = QLineEdit(str(daq["sample_rate"]))
        self.mode_combo = QComboBox()
        for label, value in (("內部按鈕", 0), ("外部輸入1：按一下開始，再按停止儲存", 1),
                             ("外部輸入2：按住擷取，放開停止儲存", 2)):
            self.mode_combo.addItem(label, value)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(engineering["trigger_mode"]))
        self.line_combo = QComboBox()
        self.line_combo.addItem("任一輸入線", "any")
        for index in range(4):
            self.line_combo.addItem(f"line{index}", index)
        self.line_combo.setCurrentIndex(self.line_combo.findData(engineering["trigger_line"]))
        self.level_combo = QComboBox()
        self.level_combo.addItem("高電位", True)
        self.level_combo.addItem("低電位", False)
        self.level_combo.setCurrentIndex(0 if engineering["active_high"] else 1)
        self.model_edit = QLineEdit(engineering["model_path"])
        self.path_edit = QLineEdit(config["save_path"])
        self.account_edit = QLineEdit(config["account"])
        content = QWidget()
        form = QFormLayout(content)
        for label, widget in (
            ("DAQ 裝置名稱", self.daq_device_edit), ("類比輸入閘道1", self.gateway1_edit),
            ("類比輸入閘道2", self.gateway2_edit), ("數位輸入閘道1", self.di_edit),
            ("按鈕觸發線", self.line_combo), ("按下有效電位", self.level_combo),
            ("數位輸出閘道1", self.do_edit), ("取樣點數（內部模式）", self.count_edit),
            ("取樣率（每秒筆數）", self.rate_edit), ("觸發模式", self.mode_combo),
        ):
            form.addRow(label, widget)
        for label, edit, directory in (("模型路徑（預留）", self.model_edit, False),
                                       ("儲存路徑", self.path_edit, True)):
            row = QHBoxLayout()
            row.addWidget(edit)
            button = QPushButton("變更路徑")
            button.clicked.connect(lambda checked=False, e=edit, d=directory: self.select_path(e, d))
            row.addWidget(button)
            form.addRow(label, row)
        form.addRow("帳號（收件 Email）", self.account_edit)
        form.addRow("通知裝置編號", self.device_edit)
        note = QLabel("每 1024 筆模擬判定一次，尚未載入 AI 模型。\n"
                      "外部模式持續至停止，最多 60 秒或 100000 筆。\n"
                      "外部檔案讀取本版暫不提供；關閉設定頁不會儲存變更。")
        note.setWordWrap(True)
        form.addRow(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)
        buttons = QHBoxLayout()
        self.btnSave = QPushButton("儲存")
        self.btnCancel = QPushButton("離開")
        self.btnSave.clicked.connect(self.save_settings)
        self.btnCancel.clicked.connect(self.reject)
        buttons.addWidget(self.btnSave)
        buttons.addWidget(self.btnCancel)
        layout.addLayout(buttons)

    def select_path(self, edit, directory):
        path = (QFileDialog.getExistingDirectory(self, "選擇儲存資料夾") if directory else
                QFileDialog.getOpenFileName(self, "選擇模型（本版僅保存路徑）")[0])
        if path:
            edit.setText(path)

    def save_settings(self):
        candidate = apply_engineering_defaults(apply_daq_defaults(deepcopy(self.config)))
        try:
            device = self.daq_device_edit.text().strip()
            candidate["daq"].update(
                channel=device + "/" + self.gateway1_edit.text().strip().lstrip("/"),
                samples_per_channel=int(self.count_edit.text()), sample_rate=float(self.rate_edit.text()),
            )
            do_line = self.do_edit.text().strip().lstrip("/")
            candidate["engineering"].update(
                trigger_mode=self.mode_combo.currentData(),
                di_channel=device + "/" + self.di_edit.text().strip().lstrip("/"),
                trigger_line=self.line_combo.currentData(), active_high=self.level_combo.currentData(),
                do_channel=device + "/" + do_line if do_line else "",
                model_path=self.model_edit.text().strip(),
            )
            candidate.update(save_path=self.path_edit.text().strip(), account=self.account_edit.text().strip(),
                             device_number=self.device_edit.text().strip())
            if not candidate["save_path"]:
                raise AcquisitionError("請填寫儲存路徑。")
            validate_engineering(candidate)
            self.save_callback(candidate)
        except (ValueError, AcquisitionError, OSError) as error:
            self.message_callback(self, QMessageBox.Icon.Warning, "工程設定未儲存", str(error))
            return
        self.config.clear()
        self.config.update(candidate)
        self.accept()
