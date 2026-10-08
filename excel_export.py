"""應用程式的 Excel 輸出；保留原始電壓，尚未量測的電流保持空白。"""

from io import BytesIO
from pathlib import Path


def save_capture_excel(folder, capture, score, prediction, saved_at):
    if len(capture.voltage) != len(capture.voltage2):
        raise ValueError("兩個電壓通道的樣本數不一致，無法儲存。")
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "擷取資料"
    sheet.append(["Timestamp", "Voltage", "Current", "Score", "Prediction", "Voltage2"])
    for voltage, voltage2 in zip(capture.voltage, capture.voltage2):
        sheet.append([saved_at, voltage, None, score, prediction, voltage2])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column, width in {"A": 23, "B": 20, "C": 18, "D": 14, "E": 18, "F": 20}.items():
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=2):
        row[0].number_format = "yyyy-mm-dd hh:mm:ss"
        row[1].number_format = "0.000000"
        row[3].number_format = "0.00"
        row[5].number_format = "0.000000"

    metadata = workbook.create_sheet("擷取設定")
    for row in [
        ["項目", "內容"],
        ["通道", capture.channel],
        ["裝置型號", capture.product_type],
        ["訊號來源", "NI-DAQmx 模擬裝置" if capture.is_simulated else "實體裝置"],
        ["端點模式", capture.terminal_config],
        ["設定電壓下限 (V)", capture.min_voltage],
        ["設定電壓上限 (V)", capture.max_voltage],
        ["實際取樣率 (samples/s)", capture.sample_rate],
        ["樣本數", len(capture.voltage)],
        ["擷取完成時間", capture.completed_at],
        ["儲存時間", saved_at],
        ["Voltage 單位", "V"],
        ["Current", "未量測，資料欄位留白"],
        ["Score / Prediction", "隨機測試判定，尚未串接 AI 模型"],
        ["Timestamp", "儲存時間，非逐筆取樣時間"],
        ["第二電壓通道", capture.channel2],
        ["Voltage2 單位", "V"],
        ["通道資料對應", "Voltage 為第一通道；Voltage2 為第二通道；同列為同次掃描樣本"],
    ]:
        metadata.append(row)
        # 設定中的文字一律以字串儲存，避免被 Excel 視為公式。
        for cell in metadata[metadata.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
            elif hasattr(cell.value, "strftime"):
                cell.number_format = "yyyy-mm-dd hh:mm:ss"
    metadata.column_dimensions["A"].width = 32
    metadata.column_dimensions["B"].width = 52
    metadata.freeze_panes = "A2"
    for table in (sheet, metadata):
        for cell in table[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E79")

    buffer = BytesIO()
    try:
        workbook.save(buffer)
    finally:
        workbook.close()
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    prefix = saved_at.strftime("%Y%m%d_%H%M%S")
    index = 1
    while True:
        path = root / f"{prefix}_{index:03d}.xlsx"
        try:
            stream = path.open("xb")
        except FileExistsError:
            index += 1
            continue
        try:
            with stream:
                stream.write(buffer.getvalue())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return str(path)
