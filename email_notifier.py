"""單一背景 SMTP 工作者；不接觸 Qt、不重試、不記錄認證內容。"""

import logging
import math
import os
import re
import smtplib
import ssl
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from queue import SimpleQueue
from threading import Condition, Thread


EMAIL_DEFAULTS = {
    "enabled": False,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "security": "ssl",
    "username": "",
    "sender": "",
    "password_env": "METAL_SMTP_PASSWORD",
    "timeout_seconds": 20,
}

logger = logging.getLogger(__name__)


def apply_email_defaults(config):
    """只補缺值，保留已有值、未知欄位及格式錯誤供驗證時說明。"""
    email = config.setdefault("email", {})
    if isinstance(email, dict):
        for key, value in EMAIL_DEFAULTS.items():
            email.setdefault(key, value)
    return config


class NotificationConfigError(ValueError):
    pass


def address(value, label):
    value = value.strip() if isinstance(value, str) else ""
    # 本版支援單一一般 ASCII 信箱；不接受地址清單或標頭換行。
    if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+", value):
        raise NotificationConfigError(f"{label}空白或格式無效，請填寫單一 Email 地址")
    local = value.split("@")[0]
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise NotificationConfigError(f"{label}格式無效")
    return value


@dataclass(frozen=True)
class MailSettings:
    smtp_host: str
    smtp_port: int
    security: str
    username: str
    sender: str
    password_env: str
    timeout_seconds: float


@dataclass(frozen=True)
class Notification:
    capture_id: int
    recipient: str
    device_number: str
    completed_at: datetime
    score: float
    prediction: str
    settings: MailSettings


def make_notification(config, capture_id, completed_at, score, prediction):
    """建立不可變快照；停用或 OK 回傳 None，錯誤交由主畫面顯示。"""
    if prediction != "NG":
        return None
    email = config.get("email", {})
    if not isinstance(email, dict):
        raise NotificationConfigError("email 必須是 JSON 物件")
    email = {**EMAIL_DEFAULTS, **email}
    if not isinstance(email["enabled"], bool):
        raise NotificationConfigError("email.enabled 必須是 true 或 false")
    if not email["enabled"]:
        return None

    def required(key):
        value = email[key]
        if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
            raise NotificationConfigError(f"email.{key} 未填寫或格式無效")
        return value.strip()

    recipient = address(config.get("account"), "收件地址 account")
    sender = address(email["sender"], "寄件地址 email.sender")
    security = required("security")
    if security not in ("ssl", "starttls"):
        raise NotificationConfigError("email.security 僅支援 ssl 或 starttls")
    port = email["smtp_port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise NotificationConfigError("email.smtp_port 必須為 1～65535 的整數")
    timeout = email["timeout_seconds"]
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise NotificationConfigError("email.timeout_seconds 必須是大於 0 的有限數值")
    settings = MailSettings(required("smtp_host"), port, security,
                            required("username"), sender,
                            required("password_env"), timeout)
    if not os.environ.get(settings.password_env):
        raise NotificationConfigError("指定的 SMTP 密碼環境變數不存在或為空，請設定後重新啟動程式")
    device = str(config.get("device_number", ""))
    if any(ord(c) < 32 for c in device):
        raise NotificationConfigError("裝置號碼不可包含換行或控制字元")
    return Notification(capture_id, recipient, device, completed_at,
                        float(score), prediction, settings)


def build_message(job):
    message = EmailMessage()
    message["Subject"] = f"【NG 異常通知】裝置 {job.device_number}"
    message["From"] = job.settings.sender
    message["To"] = job.recipient
    message.set_content(
        "金屬製造異常警示通報系統偵測到異常。\n\n"
        f"裝置號碼：{job.device_number}\n"
        f"擷取時間：{job.completed_at:%Y-%m-%d %H:%M}\n"
        f"預測分數：{job.score:.2f}\n"
        f"預測結果：{job.prediction}\n\n"
        "請確認設備狀況及本次擷取資料。\n",
        charset="utf-8",
    )
    return message


def send_notification(job):
    settings = job.settings
    password = os.environ.get(settings.password_env)
    if not password:
        raise NotificationConfigError("指定的 SMTP 密碼環境變數不存在或為空")
    context = ssl.create_default_context()
    client = None
    try:
        if settings.security == "ssl":
            client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                      timeout=settings.timeout_seconds, context=context)
        elif settings.security == "starttls":
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port,
                                 timeout=settings.timeout_seconds)
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        else:
            raise NotificationConfigError("僅允許 ssl 或 starttls 加密連線")
        client.login(settings.username, password)
        refused = client.send_message(build_message(job), from_addr=settings.sender,
                                      to_addrs=[job.recipient])
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    finally:
        # DATA 已獲接受即成功；不讓 QUIT 失敗改成寄送失敗或導致重送。
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def failure_reason(error):
    if isinstance(error, NotificationConfigError):
        return str(error)
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "SMTP 登入失敗，請確認帳號、應用程式密碼及服務商政策"
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "郵件伺服器拒絕收件地址，請確認地址及寄送權限"
    if isinstance(error, smtplib.SMTPSenderRefused):
        return "郵件伺服器拒絕寄件地址，請確認 sender 及寄送權限"
    if isinstance(error, ssl.SSLError):
        return "TLS 加密或憑證驗證失敗，未降級成明文"
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return "伺服器不支援必要的 TLS 或 SMTP 認證功能"
    if isinstance(error, TimeoutError):
        return "網路操作逾時，寄送結果可能不明；不會自動重試"
    if isinstance(error, smtplib.SMTPServerDisconnected):
        return "郵件伺服器中斷連線，寄送結果可能不明；不會自動重試"
    if isinstance(error, smtplib.SMTPException):
        return "郵件伺服器拒絕寄送或通訊失敗；不會自動重試"
    # SMTPException 也繼承 OSError，須先處理 SMTP 的具體原因。
    if isinstance(error, OSError):
        return "無法連線至郵件伺服器，請檢查主機、連接埠及網路"
    return "寄送發生未預期錯誤，請查看終端機的錯誤類型"


class EmailNotifier:
    """至多一條執行緒、100 筆等待佇列，結果由 Qt 主執行緒輪詢。"""

    def __init__(self):
        self.results = SimpleQueue()
        self._condition = Condition()
        self._pending = deque()
        self._closing = False
        self._thread = None

    def submit(self, job):
        with self._condition:
            if self._closing:
                return "程式正在關閉，通知未排入"
            if len(self._pending) >= 100:
                return "通知等待佇列已滿（100 筆），本筆未排入；不會自動重試"
            if self._thread is None:
                self._thread = Thread(target=self._run, name="metal-email", daemon=False)
                self._thread.start()
            self._pending.append(job)
            self._condition.notify()
        return None

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closing or self._pending)
                if self._closing:
                    return
                job = self._pending.popleft()
            self.results.put((job.capture_id, "通知寄送中"))
            try:
                send_notification(job)
                status = "已交給郵件伺服器"
            except Exception as error:
                status = "寄送失敗：" + failure_reason(error)
                # 不輸出 exception 本文、伺服器回應或 traceback，避免洩漏認證資料。
                logger.warning("Email capture=%s error=%s", job.capture_id, type(error).__name__)
            self.results.put((job.capture_id, status))

    def shutdown(self):
        with self._condition:
            self._closing = True
            while self._pending:
                job = self._pending.popleft()
                self.results.put((job.capture_id, "通知已取消：程式關閉，尚未開始寄送"))
            self._condition.notify_all()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def wait(self):
        if self._thread is not None:
            self._thread.join()
