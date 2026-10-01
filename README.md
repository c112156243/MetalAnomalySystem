# 金屬製造異常警示通報系統

本專案為 Python／PySide6 Windows 桌面應用程式。**按「擷取」會透過 NI-DAQmx 讀取裝置電壓，不再隨機生成 Voltage／Current；AI 模型尚未串接，Score 與 OK／NG 仍隨機決定。NG 依既有設定寄送 Email，按「儲存」輸出真正的 Excel `.xlsx`。**

本次需求與使用者確認：先使用 `Dev1/ai0`、差動 DIFF、±10 V，以設備硬體時鐘每秒 1000 筆、每次 1000 筆（約 1 秒）；電流未接入，欄位留白。主程式沒有隨機訊號備援；NI MAX 的模擬裝置仍可透過驅動讀取，畫面與 Excel 會標示來源。

## 1. 功能現況

| 功能 | 行為 |
| --- | --- |
| 擷取 | 背景執行緒讀取單一 NI 類比電壓通道，完整成功後才更新資料 |
| 預測 | `random.uniform(0.0, 1.0)`；分數 >= 0.5 為 OK，否則 NG，尚無 AI 模型 |
| Email | 成功擷取後每次 NG 各排入一封通知；OK、不成功的擷取、儲存都不寄新信 |
| Excel | 手動儲存目前這一批資料到 `save_path/YYYY/MM/DD/`，不自動寄附件 |
| 電流 | `Current` 留白，不填零、不複製電壓、不生成假電流 |
| 歷史 | 保留本次執行期間的完成時間、分數與結果，重啟不保留 |
| 設定 | 原帳號／儲存路徑設定保留；DAQ 參數目前由 JSON 設定 |

**隨機 NG 會照常寄信，這是目前刻意保留的測試流程，不代表真實設備異常。** 既有本機 Email 設定不被覆蓋；新設定檔／範本預設停用寄信。

## 2. 檔案與責任

| 檔案 | 用途 |
| --- | --- |
| `main.py` | UI、設定載入、擷取工作生命週期、隨機判定、歷史、儲存按鈕 |
| `daq_acquisition.py` | DAQ 預設值與驗證、NI-DAQmx 有限取樣、可取消背景工作者 |
| `excel_export.py` | Excel 資料與設定工作表、日期／數值格式、避免覆蓋舊檔 |
| `email_notifier.py` | 原有通知快照、SMTP 驗證及背景寄信，這次未改變通知內容 |
| `config.example.json` | 不含個資的設定範本 |
| `config.json` | 本機帳號與設備設定，Git 忽略，不可覆寫使用者已有值 |
| `requirements.txt` | 套件依賴，新增 nidaqmx 及 openpyxl |
| `ui/main_window.ui` | Qt Designer UI，本次不修改布局與元件名稱 |
| `tests/test_daq_acquisition.py` | mock NI API，驗證取樣、取消、錯誤與資源釋放 |
| `tests/test_email_notifications.py` | Qt offscreen UI、Excel 與 mock SMTP 整合測試 |

使用者自己的 `nidaqtest.py` 是獨立 On Demand 測試程式，這次不修改；主程式使用硬體時鐘有限取樣，與該程式的逐筆讀取模式不同。

## 3. 安裝、啟動與設備前置確認

1. 安裝支援 USB-6211 與作業系統的 **NI-DAQmx 驅動**。Python `nidaqmx` 套件不能取代驅動。
2. 接上 USB-6211，在 NI MAX 確認 `Dev1`、Self-Test 及 Test Panels 可正常讀取。接線須配合 DIFF，訊號須符合設備量測及共模限制。
3. 關閉 Test Panels 與其他占用類比輸入的程式。
4. 在本專案根目錄開啟 PowerShell。既有環境增裝本次依賴：

```powershell
.\.venv\Scripts\python.exe -m pip install nidaqmx==1.6.0 openpyxl==3.1.5
.\.venv\Scripts\python.exe main.py
```

新環境可建立虛擬環境後安裝完整依賴：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

目前既有環境為 Python 3.11.9／PySide6 6.11.1；本次沒有重新安裝整份 requirements。原清單部分套件的 Python 版本相容性仍須在新機確認，不要為此任意改寫整份依賴。

NI 官方參考：[Python 套件與驅動](https://github.com/ni/nidaqmx-python)、[硬體時鐘有限取樣範例](https://github.com/ni/nidaqmx-python/blob/master/examples/analog_in/voltage_acq_int_clk.py)、[USB-6211 規格](https://download.ni.com/support/manuals/375195d.pdf)。

## 4. 操作流程

1. 啟動後確認「帳號設定」的儲存路徑與收件人。若需寄信，依第 9 節完成 SMTP 設定。
2. 按「擷取」：擷取／儲存／帳號設定按鈕暫停使用，畫面事件仍可處理，可關窗取消。
3. 約 1 秒資料收齊後，顯示通道、筆數、實體或 NI 模擬裝置，以及隨機 OK／NG。實際等待還包含建立工作及驅動操作時間。
4. NG 且通知啟用時，自動排入一封背景 Email；OK 不寄信。
5. 按「儲存」：輸出本次資料 `.xlsx`，顯示完整檔案路徑；不再寄信。
6. 再次擷取成功會取代目前這批資料；歷史列只保留摘要。

擷取失敗時顯示原因、恢復按鈕，保留上一批成功資料／分數／結果，畫面會註明保留上一批；不新增歷史、不執行隨機判定、不寄新信。這時按儲存會儲存上一批成功資料。尚無成功資料時，儲存顯示無資料提示。既有已排入的 Email 不因新一次擷取失敗而取消。

## 5. 設定檔

首次取得專案時可複製 `config.example.json` 為 `config.json`；已有檔案時不可覆蓋。不複製也可啟動，由程式建立預設停用寄信的設定。

設定檔、UI 檔的位置以 `main.py` 所在目錄為基準。`save_path` 的相對路徑也相對於專案根目錄；絕對路徑則直接使用。

保留原有 `gateway1`、`gateway2`、`save_path`、`account`、`device_number`、`email`，新增：

```json
"daq": {
    "channel": "Dev1/ai0",
    "terminal_config": "DIFF",
    "min_voltage": -10.0,
    "max_voltage": 10.0,
    "sample_rate": 1000.0,
    "samples_per_channel": 1000
}
```

| 欄位 | 意義與限制 |
| --- | --- |
| `channel` | 單一 AI 通道，預設 Dev1/ai0；裝置名稱依 NI MAX。不可填通道範圍／多通道清單 |
| `terminal_config` | DIFF、RSE 或 NRSE，必須與實際接線相符 |
| `min_voltage` / `max_voltage` | 請求的電壓範圍；須在 -10～10 V 內且下限小於上限；實際支援由驅動判定 |
| `sample_rate` | 每秒樣本數，大於 0 且 <= 250000；Excel 記錄驅動回報的實際取樣率 |
| `samples_per_channel` | 每次總樣本數，2～100000 整數；本版限制單次資料長度 <= 60 秒 |

`load_config()` 為缺少的 daq／email 欄位補預設值，保留原設定及未知欄位。新增預設值先存在記憶體，帳號設定儲存時才一併寫回；本次開發不修改本機 `config.json`。不合法設定會在擷取時明確失敗，不會改用隨機訊號。

直接修改 JSON 後重新啟動程式。`gateway1`／`gateway2` 仍僅為原介面顯示，不用來連接 USB DAQ；`device_number` 為通知中的業務裝置識別碼，不等於 NI MAX 的 `Dev1`。

## 6. 擷取、預測與關閉邏輯

```text
btnCapture → capture_data()
  → CaptureWorker（凍結本次設定）
  → 建立 NI Task，設定 AI 通道及 FINITE 硬體時鐘
  → 分段 read，收齊全部樣本，釋放 Task
  → poll_capture_results() 在 Qt 主執行緒接收結果
  → complete_capture() 保留電壓資料與本次設備資訊
  → predict() 隨機分數及 OK／NG
  → 更新畫面／歷史，NG 依設定排入 Email
btnSave → save_data() → save_capture_excel()
```

- NI 設備操作都在同一條非 daemon 背景執行緒，不在 GUI 執行 `task.read()`。
- QTimer 每 50 ms 檢查工作完成；它不是取樣時鐘。
- 以約 0.1 秒資料為單位分段讀取，最後一段收剩餘筆數；各次 read 的 timeout 為該段時間 + 2 秒。
- 樣本不足或非有限數值視為整批失敗，不採用部分資料，不自動重試。
- 關窗設定取消旗標，下一次分段讀取前／完成後檢查；等待工作者離開 `with nidaqmx.Task()` 釋放裝置。Qt 事件迴圈保持運作，取消的資料不判定、不寄信。
- 驅動初始化、裝置查詢等仍可能受驅動影響，read timeout 並非關閉總時間保證；不強制終止執行緒。
- 等待擷取及正在寄送的 Email 均完成清理後才關窗。`QApplication.quit()` 替代路徑也會取消並 join。
- `predict()` 保留原來 >= 0.5 判 OK 的規則；訊號完全不參與分數計算。未來 AI 的前處理、模型輸入、分數意義與閾值仍未定義。

## 7. Excel 輸出

檔案範例：`data/2026/09/24/20260924_150000_001.xlsx`。同秒再次儲存依序使用 `_002`、`_003`，以獨占建立檔案避免覆蓋既有檔案。失敗保留記憶體資料供重試。

工作表「擷取資料」保留原來五個欄位；預設 1000 筆資料加 1 列標題：

| 欄位 | 內容 |
| --- | --- |
| `Timestamp` | 儲存時間，Excel 日期型別；不是逐筆取樣時間 |
| `Voltage` | NI-DAQmx 回傳的原始電壓數值，單位 V；顯示六位小數，保留底層精度 |
| `Current` | 空白儲存格；本版沒有量測電流 |
| `Score` | 本批隨機分數，數值型別 |
| `Prediction` | 本批隨機 OK／NG |

工作表「擷取設定」包含本次通道、裝置型號、實體／模擬來源、端點模式、請求量測範圍、實際取樣率、樣本數、擷取完成時間與儲存時間，也標示電流未量測、尚無 AI 模型。這些資料來自擷取結果快照，之後更改設定不會改寫舊批次來源。

檔案有標題格式、欄寬、凍結標題及資料篩選，不需要安裝 Excel 即可產生檔案。原 CSV 不刪除、不轉換；新按鈕流程僅輸出 `.xlsx`，不是將 CSV 改副檔名。

## 8. 錯誤排除與驗證

| 情況 | 處理 |
| --- | --- |
| 缺 nidaqmx／NI-DAQmx | 依第 3 節安裝 Python 套件及設備驅動 |
| -50103 資源占用 | 關閉 NI MAX Test Panels 或其他正在使用 AI 的程式 |
| -200220 裝置名稱錯誤 | 檢查 USB 與 NI MAX 的裝置名稱 |
| -200170 通道錯誤 | 檢查 `daq.channel` 與設備支援通道 |
| -200284 讀取逾時 | 檢查裝置狀態、取樣設定及接線；本批不採用 |
| 儲存失敗 | 確認 save_path 權限、磁碟空間及 openpyxl 已安裝，再按儲存 |

自動測試（不接觸實體硬體，不寄出真實郵件）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git diff --check
```

NI I/O Trace 可在啟動擷取前開始記錄 NI-DAQmx 呼叫，確認通道、FINITE 時序、Read 成功及 ClearTask。通訊成功不等於量測準確，需以已知且符合設備範圍的訊號對照；NI 模擬裝置測試也不能取代實體驗證。

人工驗收：按一次擷取確認 1000 筆、分數與歷史；NG 依既有 Email 設定確認收信；按儲存檢查日期目錄與兩張 Excel 工作表、Current 留白；測試未接設備／被占用提示、擷取中關閉、同秒重複儲存。原生 Windows 顯示、真實 SMTP 及 Excel 桌面開啟需另行實測。

## 9. NG Email 通知與設定教學

### 觸發與畫面狀態

`complete_capture()` 取得分數及結果後，沿用擷取工作者記錄的完成時間，先保留擷取結果與歷史，再呼叫 `notify_capture_completed()`。只有 NG 且啟用通知才排入背景工作；每次 NG 各一封，不比較前一次結果。儲存 Excel、更新歷史與帳號設定都不寄信。

- 收件人、裝置號碼、完成時間、分數、結果及寄件設定都是當次不可變快照；工作者不讀取 `current_score` 或 `current_prediction`。密碼只在執行時從快照所指定的環境變數取得，不放進快照或設定檔。
- 繁體中文主旨與內文使用 UTF-8；分數兩位小數、擷取時間 `YYYY-MM-DD HH:MM`；沒有附件。
- 在既有底部 `QStatusBar` 加入獨立 Email 文字，不修改 `.ui` 配置，也不覆蓋 `lblStatus` 的擷取／儲存狀態。
- 顯示未啟用、等待寄送、寄送中、已交給郵件伺服器、設定錯誤或寄送失敗。最新擷取以編號與完成時間標記；較舊通知的結果只更新對應歷史列「預測結果」儲存格的滑鼠提示，不冒充最新結果。
- 「已交給郵件伺服器」僅代表 SMTP 接受，不能保證進入收件匣。關窗後歷史及通知狀態不持久化。

### 寄件設定

保留 `config.json` 原有頂層欄位，新增下列區塊（專案已加入，交付值如下）：

```json
"email": {
    "enabled": false,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "security": "ssl",
    "username": "",
    "sender": "",
    "password_env": "METAL_SMTP_PASSWORD",
    "timeout_seconds": 20
}
```

| 欄位 | 要填寫的內容 |
| --- | --- |
| 頂層 `account` | 單一收件 Email；也可從「帳號設定 → 帳號」修改並儲存，下一次 NG 即使用新地址 |
| `email.enabled` | 全部設定完成後將 `false` 改成 `true`（JSON 布林值，不加引號） |
| `email.smtp_host` | 郵件服務商提供的 SMTP 主機；Gmail 範例為 `smtp.gmail.com` |
| `email.smtp_port` | Gmail SSL 使用整數 `465`；STARTTLS 使用 `587` |
| `email.security` | `ssl` 或 `starttls`；TLS 失敗不會改用明文 |
| `email.username` | SMTP 登入帳號；Gmail 為完整寄件信箱地址 |
| `email.sender` | 寄件 Email；Gmail 通常填與 username 相同的地址，其他地址須先獲服務商授權 |
| `email.password_env` | 保留 `METAL_SMTP_PASSWORD`，或填另一個環境變數名稱；此欄不是密碼 |
| `email.timeout_seconds` | 大於 0 的網路操作逾時秒數，預設 `20` |

地址驗證支援單一一般 ASCII 信箱，不接受多位收件人清單、顯示名稱或國際化信箱。舊設定沒有 email 區塊時仍可啟動；部分欄位缺少時逐一補值。啟用後設定不足會顯示原因，不影響擷取及儲存。

### Gmail 兩步驟驗證與應用程式密碼

以下官方頁面已於 **2026-09-17** 查核：

1. 開啟 [Google 帳戶](https://myaccount.google.com/)，進入「安全性與登入」，在「登入 Google 的方式」啟用兩步驟驗證，依畫面完成。見 [Google 官方：開啟兩步驟驗證](https://support.google.com/accounts/answer/185839?hl=zh-Hant)。
2. 前往 [應用程式密碼管理](https://myaccount.google.com/apppasswords)，為本系統建立應用程式密碼，將產生的密碼放入下一節的 Windows 環境變數。不要填一般 Google 登入密碼，也不要貼到對話、程式碼或 JSON。應用程式密碼需要先啟用兩步驟驗證；公司／學校帳戶、只使用安全金鑰或開啟進階保護的帳戶可能不提供此選項。變更 Google 帳戶密碼後，需要重新建立應用程式密碼。見 [Google 官方：使用應用程式密碼](https://support.google.com/accounts/answer/185833?hl=zh-Hant)。
3. 使用 `smtp.gmail.com`、SSL 465，或 STARTTLS 587；以完整寄件地址及應用程式密碼驗證。見 [Google Workspace 官方 SMTP 設定](https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app?hl=en)。

Gmail 僅是設定範例。本版採 SMTP 帳號／密碼驗證，**不直接支援 OAuth**；若服務商或機構政策要求 OAuth，需另行整合，不能以此實作繞過要求。

### Windows 設定密碼環境變數

持久設定方式：Windows 搜尋「編輯帳戶的環境變數」→「使用者變數」→「新增」，名稱填 `METAL_SMTP_PASSWORD`，值填剛產生的應用程式密碼並儲存。密碼不要存進專案檔案。環境變數並不是加密的憑證保管庫，同一帳戶下的程式可能讀取。

若只要在目前 PowerShell 暫時使用，可執行以下互動輸入；密碼不會出現在輸入畫面或命令歷史中的文字常值：

```powershell
$smtpSecret = Read-Host '請輸入 SMTP 應用程式密碼' -AsSecureString
$smtpCredential = New-Object System.Net.NetworkCredential('', $smtpSecret)
$env:METAL_SMTP_PASSWORD = $smtpCredential.Password
Remove-Variable smtpSecret, smtpCredential
.\.venv\Scripts\python.exe main.py
```

持久環境變數儲存後，**關閉並重新開啟本系統，以及用來啟動它的 PowerShell／Windows Terminal、IDE 或其他啟動器**，再啟動本系統；既有 Python 程序不會自動取得新值。如果啟動器仍繼承舊環境，可登出 Windows 後重新登入。上方暫時設定只影響該 PowerShell 與從它新啟動的子程序，不會更新已開啟的系統視窗。

直接編輯 JSON 的 Email 設定後也請重啟本系統。「帳號設定」儲存收件地址則會即時重載，無須重啟；已排入的通知保留舊快照。

### 手動驗證一封 NG 通知

1. 先設定自己可查看的收件地址 `account`，填好寄件 `username`、`sender`、SMTP 設定及密碼環境變數。
2. 將 `email.enabled` 改為 `true`，儲存 JSON，從已取得環境變數的終端機啟動本系統。
3. 按一次「擷取」。若為 OK 就不寄信，可再按一次；**首次出現 NG 後停止繼續擷取**，等待底部 Email 狀態變為「已交給郵件伺服器」或可理解的錯誤原因。
4. 到收件匣及垃圾郵件匣確認主旨、裝置號碼、該次擷取時間、兩位小數分數及 NG；郵件不含附件。可按「儲存」確認不會再次寄送。
5. 測試後若尚不準備持續寄信，將 enabled 改回 false 並重啟系統。不要在狀態尚不明時反覆觸發 NG，因為每次新擷取都是獨立通知。

**`predict()` 目前仍產生隨機分數與判定，通知啟用後所有模擬 NG 都會寄信，不代表真實設備異常。**

### 背景工作、錯誤與關閉策略

- 一條非 daemon Python 背景執行緒依序寄送；最多 100 筆等待通知，超過時該次顯示「佇列已滿、本筆未排入」，仍保留擷取結果。不會隨擷取次數增加執行緒。
- 工作者只寫入 thread-safe 結果佇列；主執行緒每 100 ms 由 QTimer 取得結果並更新 Qt 控制項。
- SMTP 使用系統信任憑證與主機名稱驗證。SSL 直接加密；STARTTLS 成功後才登入。無明文降級、無自動重試。
- 登入失敗、收件人被拒、網路逾時、TLS 或其他錯誤都會顯示分類原因；終端機只記錄擷取編號及錯誤類型，不輸出密碼、SMTP 完整回應、認證資料或 traceback。逾時／斷線有可能發生在伺服器已接受後，寄送結果可能不明。
- 按離開或標題列關閉時，取消尚未完成的 NI 擷取、取消尚未開始的通知、停止接受新通知。如果仍有擷取工作或正在寄送的一封，視窗暫緩關閉，事件迴圈持續運作並顯示等待文字；擷取與寄信工作者均結束且 join 後才關閉。
- 不強制殺死執行緒。`timeout_seconds` 是每次 socket 操作的逾時，**不是整封信或關閉等待的總時間上限**；多次 SMTP 操作及作業系統 DNS 解析可能使等待較長。直接呼叫 `QApplication.quit()` 時，事件迴圈退出後仍會取消擷取、取消等待佇列並 join 兩種工作者；此替代路徑不再提供等待畫面。強制終止程序不在優雅關閉保證範圍內。
- 待寄通知只在記憶體，不持久化；關閉取消後不會在下次啟動補寄。

## 10. 給 Codex／後續維護者的任務規格

1. 先閱讀 AGENTS.md、README.md、當前程式，確認分支與未提交變更；不提交、不推送，不覆蓋使用者的 nidaqtest.py、本機 config.json 或資料。
2. 本次需求已明確授權「DAQ 真實讀值 + 隨機 OK／NG + NG Email + 手動 Excel 儲存」。**不要自行停用隨機判定／NG 通知，也不要宣稱已完成 AI 模型。**
3. 預設只擷取 Dev1/ai0，DIFF、±10 V、1000 samples/s、1000 samples。Current 留白，不假造第二通道或安培換算。
4. 只有完整成功的擷取才進入 predict／history／notify；設備錯誤不得退回假資料。
5. 所有 DAQ 操作在背景執行，UI 更新在主執行緒。修改生命週期時一併驗證關窗取消、等待釋放、沒有晚到的寄信。
6. Email 收件人、啟用狀態、憑證環境變數與背景佇列沿用第 9 節；不得把個資、密碼寫進測試或版本控制。SMTP 測試預設 mock。
7. 新資料輸出真正 `.xlsx`，使用者儲存路徑與年月日結構保留；防止同秒覆蓋。檢查全部 Voltage 原值、Current 空白、分數／判定及擷取設定快照。
8. 不為本次工作另行重構 UI、增加 AI、增加第二通道、重寫全部依賴或改變通知內容。若未來加入電流，要先確定感測器與轉換比例。
9. 執行相關測試；分別報告 mock、自動實體擷取、原生 UI、真實寄信的實際驗證範圍，不得混為全部已驗證。
10. 修改完成更新 README，記錄變更、測試結果、待確認事項與 Asia/Taipei 完成時間。

## 11. 歷史紀錄說明

以下第 12、13 節保留既有開發歷史，當時的模擬擷取／CSV 敘述僅適用舊版本；目前行為以第 1～10 節與最新開發紀錄為準。

## 12. Email 功能開發紀錄（2026-09-17）

修改完成時間：**2026-09-17 19:22（Asia/Taipei，UTC+08:00）**。

本次直接修改可寫入的 `C:\MetalAnomalySystem`，不需替換工作副本。開始時分支為 `main`，`config.json` 已有使用者變更，`README.md`、`AGENTS.md` 尚未追蹤；原有設定值均保留。本次修改 `main.py`、`config.json`、`README.md`，新增 `email_notifier.py` 與 `tests/test_email_notifications.py`。已閱讀且未改動 `ui/main_window.ui`；未更改依賴、提交或推送。

測試命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

結果：**16 項測試全部通過**（Python 3.11.9、PySide6 6.11.1，約 4.5 秒）。使用真正的 QUiLoader、Qt offscreen 視窗與事件迴圈，SMTP_SSL／SMTP 工廠皆替換成 mock；沒有連線至郵件服務，也沒有使用真實帳號密碼。測試所需環境變數值於執行時隨機產生，不寫入測試資料。`git diff --check` 通過，僅有 Git 的 LF／CRLF 提示。

| 驗證項目 | 結果 |
| --- | --- |
| OK 無寄信工作；NG 一封；連續兩次 NG 各一封、同一工作者 | 通過 |
| 實際擷取按鈕與 1 秒 QTimer 流程 | 通過 |
| 儲存 CSV／新增歷史不再寄信；CSV 保留 1000 筆及既有欄位 | 通過 |
| 設定對話框儲存 account、重新讀取、下一次使用新地址 | 通過 |
| 寄送中再次擷取：收件人、裝置、時間、分數及寄件設定快照不變 | 通過 |
| 舊通知不覆蓋最新 OK、正在擷取或儲存狀態 | 通過 |
| 缺 email／部分欄位：舊設定載入及視窗初始化正常、未知欄位保留 | 通過 |
| 缺密碼、缺必要設定、空白／無效地址、無效安全模式／port／timeout | 通過，顯示設定錯誤並保留擷取 |
| 登入失敗、網路逾時、連線失敗、收件拒絕、TLS／SMTP／其他錯誤 | 通過，保留歷史與 CSV、不自動重試 |
| SSL 憑證檢查、STARTTLS 先於登入、TLS 失敗後不登入／不降級 | 通過（mock 呼叫順序與 context 檢查） |
| 繁體中文主旨／內文序列化與解碼、完成時間、兩位小數、無附件 | 通過 |
| SMTP 已接受後清理連線失敗，不誤報寄送失敗 | 通過 |
| 寄送中按離開：取消待寄、Qt 仍可處理事件、等待工作者退出 | 通過，沒有執行緒銷毀警告 |
| 擷取中關閉 self.ui：停止擷取 timer、不產生新通知 | 通過 |
| 等待佇列上限與錯誤日誌不含認證內容 | 通過 |

尚未實際驗證：真實 SMTP 網路／TLS 握手、服務商登入政策、收件匣投遞、原生 Windows 桌面的人工操作與不同 DPI 顯示。另做了 offscreen 畫面輸出，確認通知位於底部獨立列；但該平台的字型渲染呈現方框，不能據此宣稱原生桌面的文字顯示已驗證。測試中的訊息對話框已 mock，未人工點選。需使用者填寫寄件帳號、寄件地址、密碼環境變數並確認收件地址後，依第 9 節手動試寄。Google Workspace 或其他郵件服務的實際允許方式仍須以該帳戶政策為準。

## 13. 推送前檢查（2026-09-19）

本次依使用者指示，將功能整理至 `feature/email-notification` 分支。已閱讀 `.gitignore`，保留對虛擬環境、資料、日誌及 `AGENTS.md` 的忽略規則；新增忽略本機 `config.json`，改提供 `config.example.json`。本機已設定的收寄信地址與啟用狀態保留，不將個人設定加入提交。

檢查時修正 SMTP 例外分類順序：`SMTPException` 繼承 `OSError`，須先辨識 SMTP 斷線與拒送，才能顯示正確原因及寄送結果可能不明的提示。另修正 README 的擷取 timer 說明。

驗證命令同第 12 節；新增 SMTP 斷線／拒送分類及缺少本機設定時自動建立停用預設值的測試。真實 SMTP 及原生桌面人工驗證限制仍同上節。

本次修改與檢查完成時間：**2026-09-19 12:31（Asia/Taipei，UTC+08:00）**。共 **18 項測試全部通過**（4.357 秒），`git diff --check` 與暫存區格式檢查通過；忽略規則確認排除本機設定、AGENTS.md、虛擬環境、CSV 資料及 Python 快取。


## 14. NI DAQ 與 Excel 功能開發紀錄（2026-09-24）

修改完成時間：**2026-09-24 14:20:14（Asia/Taipei，UTC+08:00）**。

開始時分支為 `feature/email-notification`，已有使用者未追蹤的 `nidaqtest.py`，本次保留不動。修改 `main.py`、`config.example.json`、`requirements.txt`、`tests/test_email_notifications.py`、本 README；新增 `daq_acquisition.py`、`excel_export.py`、`tests/test_daq_acquisition.py`。沒有修改本機 `config.json`、`email_notifier.py`、`.ui` 或既有資料，沒有提交或推送。

變更：UI 擷取改走背景 NI-DAQmx 硬體有限取樣；只讀電壓，電流空白；保留原隨機判定與 NG 通知；CSV 儲存改為 Excel，加入本次來源設定快照與防覆寫檔名；補齊錯誤及關閉處理、狀態文字換行、給 Codex 的完整執行規格。

### 自動測試

`python -m unittest discover -s tests -v`：**34 項測試全部通過（5.081 秒）**。使用既有 Python 3.11.9、PySide6 6.11.1、nidaqmx 1.6.0，以及本次安裝的 openpyxl 3.1.5。DAQ API 與 SMTP 均 mock，不操作設備或寄出真實郵件。`py_compile` 與 `git diff --check` 通過（僅 Git LF／CRLF 提示）。

涵蓋：有限取樣參數與完整原值、最後不足一段的讀取、驅動回報取樣率、取消及釋放、缺驅動／套件、占用／裝置／通道／逾時、非有限／不足樣本、無效設定；按鈕啟動背景工作、重複擷取防護、UI 事件仍運作、關窗後不寄新信、失敗保留上一批及可再次擷取；Excel 1000 筆原值、空白 Current、數值與日期型別、原五欄、metadata 快照、同秒不同檔名、目錄／寫入失敗復原、無資料提示；既有 NG／OK 通知、連續 NG、收件設定變更、SMTP 錯誤及關閉策略等。

### 實體 NI-DAQmx 驗證

在一般 Windows 執行環境，直接呼叫本次 `acquire_voltage()`，成功取得：

| 項目 | 結果 |
| --- | --- |
| 型號／來源 | USB-6211；is_simulated = False |
| 通道／模式 | Dev1/ai0；DIFF；±10 V；硬體 FINITE |
| 樣本數 | 1000 |
| 實際取樣率 | 1000.0 samples/s |
| 電壓最小／最大 | 約 -0.030580314 / +0.011515767 V |
| 執行結果 | 正常返回並釋放 Task，未寄信 |

受限執行環境的首次驅動讀取未完成，已停止該次驗證；在獲允許的一般 Windows 環境重新執行有 30 秒外部上限的獨立測試後成功。這個 30 秒上限只屬於驗證程序，不是主程式的強制終止策略。

### 尚待確認

- 以上實體測試驗證單獨擷取模組；UI 按鈕與其餘功能鏈透過 mock／Qt offscreen 測試。尚未人工完成原生 UI → 實體擷取 → 真實 NG 收信 → Excel 桌面開啟的整套流程。
- 未知當時輸入訊號與接線，不可把約零電壓的讀值視為量測準確度或感測器校正通過。
- 已產生並查看 offscreen UI 截圖，確認狀態區可換行；該平台中文字型仍呈方框，因此原生 Windows 字型／DPI 顯示待人工確認。
- Excel 已使用 openpyxl 重新開啟檢查結構與全批數值；尚未在 Microsoft Excel 桌面人工檢查。
- 真實 SMTP 登入、網路與收件匣投遞沿用既有設定，本次未寄送實際測試信。AI 模型與電流感測器仍未接入，依使用者要求保留隨機 OK／NG。
