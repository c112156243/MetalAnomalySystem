# 金屬製造異常警示通報系統

本專案是一個以 Python 與 PySide6 開發的繁體中文桌面應用程式，用於金屬製造異常監測的操作流程展示與後續整合開發。目標流程為：取得電壓／電流資料、進行模型判定、顯示 OK／NG、儲存資料，並在 NG 時通知指定人員。

**目前是模擬擷取與模擬預測版本。畫面上的結果不是來自真實設備或已訓練模型；NG Email 通知已實作，交付時預設停用。啟用後，隨機模擬產生的 NG 也會寄信。**

本文依 2026-09-17 讀取的 `main.py`、`config.json`、`ui/main_window.ui`、`requirements.txt` 與本機虛擬環境資訊整理。後續若程式變更，請以實際程式為準並同步更新本文。

## 1. 功能現況

| 功能 | 狀態 | 說明 |
| --- | --- | --- |
| 桌面操作介面 | 已實作 | 顯示閘道位置、分數、預測結果、歷史紀錄及操作狀態 |
| 擷取按鈕 | 已實作，使用模擬資料 | 約等待 1 秒後產生電壓、電流資料 |
| OK／NG 判定 | 已實作，使用隨機分數 | 尚未載入模型，分數不由電壓／電流計算 |
| 歷史紀錄 | 已實作 | 顯示本次執行期間的時間、分數與結果 |
| CSV 儲存 | 已實作 | 使用者手動儲存目前這一批資料 |
| 帳號設定視窗 | 已實作 | 修改閘道位置、儲存路徑、帳號及裝置號碼 |
| 真實設備通訊 | 未實作 | 目前閘道位置僅供設定與顯示 |
| 1D CNN 推論 | 未實作 | 程式註解記載的未來整合方向 |
| NG Email 通知 | 已實作，預設停用 | 每次 NG 完成後，背景寄送至當時已載入的 `account`；無 CSV 附件 |

## 2. 檔案結構

```text
MetalAnomalySystem/
├── main.py                 # 程式入口、視窗控制、模擬擷取、預測及 CSV 儲存
├── email_notifier.py       # 通知快照、SMTP 驗證及單一背景寄信工作者
├── config.example.json     # 可提交的設定範本，通知預設停用
├── config.json             # 本機使用者設定（Git 忽略）
├── requirements.txt        # 專案列出的 Python 套件與版本
├── README.md               # 專案說明
├── .gitignore              # 排除虛擬環境、產生的資料、日誌等
├── ui/
│   └── main_window.ui      # Qt Designer 主視窗配置
├── tests/
│   └── test_email_notifications.py  # PySide6 offscreen + mock SMTP 功能測試
├── data/                   # 預設資料輸出目錄，執行後可自動建立
│   └── YYYY/MM/DD/
│       └── YYYYMMDD_HHMMSS_001.csv
└── .venv/                  # 本機虛擬環境，其他電腦應重新建立
```

設定檔與 UI 檔位置以 `main.py` 所在目錄為基準。`save_path` 若是相對路徑，也相對於該目錄解析；若是絕對路徑，則使用指定位置。

## 3. 安裝與啟動

目前開發情境為 Windows。既有 `.venv/pyvenv.cfg` 記錄 Python 3.11.9，但這不代表已確認目前 `requirements.txt` 中所有固定版本都支援 Python 3.11。

在專案根目錄開啟 PowerShell。新環境可依下列流程建立與安裝，使用與依賴版本相容的 Python：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

若 `.venv` 已存在且可用，可直接執行最後一行啟動程式。若安裝失敗，應依錯誤檢查 Python 版本與依賴相容性，不要任意重寫整份依賴清單。

目前 `main.py` 直接使用 PySide6 與 Python 標準函式庫；`requirements.txt` 另列有 NumPy、pandas、Matplotlib、scikit-learn 等套件，其存在不代表目前已完成繪圖、資料分析或模型推論。

本次在既有 Python 3.11.9／PySide6 6.11.1 虛擬環境執行 Qt offscreen 功能測試，沒有重新安裝依賴。SMTP 功能僅使用 Python 標準函式庫。

## 4. 使用流程

1. 啟動程式，讀取設定並建立當日資料目錄。
2. 按「帳號設定」，填寫閘道位置、儲存路徑、帳號與裝置號碼，再儲存變更。
3. 按「擷取」，等待約 1 秒，程式產生模擬資料並更新分數與 OK／NG 結果。
4. 擷取結果加入畫面上的歷史紀錄；若為 NG 且通知已啟用，立即排入一封背景通知。
5. 如需保留原始資料，按「儲存」輸出目前這一批 CSV。
6. 按「離開」關閉主視窗。

每次擷取會取代記憶體中的目前電壓、電流與預測結果。歷史表格保留摘要，但目前沒有持久化或重新載入歷史紀錄的功能。

## 5. 設定檔

從儲存庫初次取得程式時，複製 `config.example.json` 為 `config.json` 再填寫本機設定；若不複製，程式也會自動建立預設停用通知的設定。已有 `config.json` 時請勿覆蓋。實際設定含個人信箱，因此不再納入 Git；只提交不含個資的範本。

以下為格式範例，實際值請依使用環境填寫：

```json
{
    "gateway1": "192.168.1.101",
    "gateway2": "192.168.1.102",
    "save_path": "data",
    "account": "recipient@example.com",
    "device_number": "DEVICE001"
}
```

| 欄位 | 用途 | 目前行為 |
| --- | --- | --- |
| `gateway1` | 第一個閘道位置 | 顯示於電壓區塊，尚未建立設備連線 |
| `gateway2` | 第二個閘道位置 | 顯示於電流區塊，尚未建立設備連線 |
| `save_path` | CSV 儲存根目錄 | 自動依年／月／日建立子目錄 |
| `account` | NG 通知收件地址 | 使用當次已載入的值並去除頭尾空白；不是 SMTP 登入帳號 |
| `device_number` | 裝置識別碼 | 目前可編輯與儲存；現有 CSV 未包含此欄位 |

`load_config()` 在設定檔不存在時建立預設設定；讀取成功後會補上缺少的頂層欄位及 `email` 中每個缺少的欄位，保留已有值及其他欄位。新增的預設值先存在記憶體，帳號設定儲存時會一併寫入。讀取發生例外時，會在終端機顯示錯誤並使用預設設定。完整 Email 欄位見第 9 節。

透過設定視窗儲存後，主視窗會重新讀取設定。直接從外部編輯 JSON 不會自動觸發即時重載，通常需重啟程式。

## 6. 擷取與預測邏輯

目前流程如下：

```text
按下「擷取」
    → capture_data()
    → 單次 _capture_timer.start(1000)，完成後呼叫 generate_test_data()
    → 產生電壓、電流各 1000 筆
    → predict() 產生隨機分數並判定 OK／NG
    → 更新目前資料、畫面及歷史紀錄
    → NG 且啟用通知：建立本次快照並排入背景寄信
    → 等待使用者按「儲存」
```

- Voltage 模擬範圍：4.8～5.2。
- Current 模擬範圍：0.8～1.2。
- Score 模擬範圍：0.0～1.0。
- `score >= 0.5` 判為 `OK`，否則判為 `NG`。
- 分數與模擬訊號彼此獨立，不應將此隨機分數解讀為正式模型的異常機率。
- OK 顯示綠色背景，NG 顯示紅色背景。

未來預計整合 `Voltage + Current → preprocessing → 1DCNN → probability → OK / NG`。目前尚未定義正式的模型檔、輸入形狀、前處理參數、機率意義或判定閾值，不能直接假設正式模型沿用模擬版的分數方向。

## 7. CSV 輸出

輸出路徑範例：

```text
data/2026/09/17/20260917_143025_001.csv
```

使用 `utf-8-sig` 編碼，欄位如下：

| 欄位 | 內容 |
| --- | --- |
| `Timestamp` | 按下儲存時的時間，格式為 `YYYY-MM-DD HH:MM:SS` |
| `Voltage` | 該筆電壓值 |
| `Current` | 該筆電流值 |
| `Score` | 該批擷取的分數 |
| `Prediction` | 該批擷取的 OK／NG 結果 |

目前每次模擬擷取儲存後，CSV 會有一列標題及 1000 列資料。同一批資料共用儲存時間、分數及判定；`Timestamp` 不是每個樣本各自的採樣時間，也不一定等於擷取完成時間。

檔名尾碼目前固定為 `_001`，不是自動遞增編號。同一秒內若寫入相同檔名，現有寫入方式可能覆蓋舊檔。

## 8. 程式維護入口

| 位置 | 職責 |
| --- | --- |
| `load_config()` / `save_config()` | 讀寫 JSON 設定 |
| `create_today_folder()` | 解析儲存路徑並建立當日目錄 |
| `SettingsDialog` | 建立與儲存設定視窗 |
| `MainWindow.__init__()` | 載入 UI、設定、元件與事件連線 |
| `capture_data()` | 開始模擬擷取及更新執行中狀態 |
| `generate_test_data()` | 產生資料、取得預測、更新畫面與歷史 |
| `predict()` | 目前為隨機判定，未來模型整合入口 |
| `add_history()` | 加入歷史摘要 |
| `save_data()` | 儲存目前這一批 CSV |
| `open_settings()` | 開啟設定視窗並套用已儲存設定 |
| `main()` | 建立 QApplication 並啟動事件迴圈 |

UI 使用 `QUiLoader` 在執行時載入 `.ui` 檔。重要元件名稱包括 `btnCapture`、`btnSave`、`btnSettings`、`btnExit`、`lblScore`、`lblPrediction`、`lblStatus`、`lblGateway1`、`lblGateway2` 及 `tableHistory`。修改名稱時必須同步調整 Python 中的查找與引用。

**關閉事件：** `MainWindow` 現在繼承 `QObject`，透過 `self.ui.installEventFilter(self)` 攔截實際顯示視窗的關閉事件。「離開」、標題列關閉都走相同流程；不依賴外層 Python 類別的 `closeEvent()`。策略詳見第 9 節。

## 9. NG Email 通知與設定教學

### 觸發與畫面狀態

`generate_test_data()` 取得分數及結果後，記錄本次完成時間，先保留擷取結果與歷史，再呼叫 `notify_capture_completed()`。只有 NG 且啟用通知才排入背景工作；每次 NG 各一封，不比較前一次結果。儲存 CSV、更新歷史與帳號設定都不寄信。

- 收件人、裝置號碼、完成時間、分數、結果及寄件設定都是當次不可變快照；工作者不讀取 `current_score` 或 `current_prediction`。密碼只在執行時從快照所指定的環境變數取得，不放進快照或設定檔。
- 繁體中文主旨與內文使用 UTF-8；分數兩位小數、擷取時間 `YYYY-MM-DD HH:MM`；沒有 CSV 附件。
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
4. 到收件匣及垃圾郵件匣確認主旨、裝置號碼、該次擷取時間、兩位小數分數及 NG；郵件不含 CSV。可按「儲存」確認不會再次寄送。
5. 測試後若尚不準備持續寄信，將 enabled 改回 false 並重啟系統。不要在狀態尚不明時反覆觸發 NG，因為每次新擷取都是獨立通知。

**`predict()` 目前仍使用隨機測試資料，通知啟用後所有模擬 NG 都會寄信，不代表真實設備異常。**

### 背景工作、錯誤與關閉策略

- 一條非 daemon Python 背景執行緒依序寄送；最多 100 筆等待通知，超過時該次顯示「佇列已滿、本筆未排入」，仍保留擷取結果。不會隨擷取次數增加執行緒。
- 工作者只寫入 thread-safe 結果佇列；主執行緒每 100 ms 由 QTimer 取得結果並更新 Qt 控制項。
- SMTP 使用系統信任憑證與主機名稱驗證。SSL 直接加密；STARTTLS 成功後才登入。無明文降級、無自動重試。
- 登入失敗、收件人被拒、網路逾時、TLS 或其他錯誤都會顯示分類原因；終端機只記錄擷取編號及錯誤類型，不輸出密碼、SMTP 完整回應、認證資料或 traceback。逾時／斷線有可能發生在伺服器已接受後，寄送結果可能不明。
- 按離開或標題列關閉時，停止尚未完成的模擬擷取、取消尚未開始的通知、停止接受新通知。如果有正在寄送的一封，視窗暫緩關閉，事件迴圈持續運作並顯示等待文字；工作者結束且 join 後才關閉。
- 不強制殺死執行緒。`timeout_seconds` 是每次 socket 操作的逾時，**不是整封信或關閉等待的總時間上限**；多次 SMTP 操作及作業系統 DNS 解析可能使等待較長。直接呼叫 `QApplication.quit()` 時，事件迴圈退出後仍會取消等待佇列並 join；此替代路徑不再提供等待畫面。強制終止程序不在優雅關閉保證範圍內。
- 待寄通知只在記憶體，不持久化；關閉取消後不會在下次啟動補寄。

## 10. 給 Codex／後續維護者

1. 先閱讀適用的 `AGENTS.md` 及實際程式，再判斷本次修改範圍。README 的待辦內容不代表每次任務都要全部實作。
2. 若在上傳專案鏡像中工作，遵守唯讀與同步檔案限制；需要時建立可寫入副本，勿更動唯讀來源。
3. 保留既有使用者設定與擷取資料，勿以範例值覆蓋。
4. 區分模擬功能與正式功能；不要宣稱已接通設備、載入模型或寄出郵件，除非已有驗證證據。
5. 除非本次需求必要，不要順帶重構整個介面、改變 CSV 欄位或改動判定方向。
6. 新增設備或網路工作時，避免阻塞 GUI，並設計好執行緒與視窗的生命週期。
7. 依修改範圍驗證啟動、設定儲存、擷取、歷史紀錄、CSV 與新增功能；清楚說明無法執行的檢查。
8. 完成修改後同步更新 README，列出實際變更、驗證結果與仍待使用者設定的項目。

## 11. 基本人工檢查清單

- 程式可載入主視窗，顯示設定中的兩個閘道位置。
- 未擷取即按「儲存」，會提示目前沒有資料。
- 按「擷取」後有執行中狀態，完成後可再次擷取。
- 分數、OK／NG 顏色及新增歷史紀錄一致。
- 儲存後，在設定路徑下產生日期資料夾與 CSV。
- CSV 欄位與當次擷取內容一致。
- 修改設定後會寫入 JSON，重新啟動仍可讀取。
- 啟用 Email 後：驗證 OK 不寄、NG 每次一封、設定變更生效、寄送失敗不影響擷取，以及關閉時的工作處理。

以上是驗證建議清單，不是已通過的測試報告。

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
