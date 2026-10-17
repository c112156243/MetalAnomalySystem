"""USB-6211 靜態數位 I/O；同一背景工作持有及釋放 Task。"""

from contextlib import ExitStack
from queue import Queue
from threading import Event, Thread
from time import monotonic


class ButtonDebouncer:
    def __init__(self, seconds=0.05):
        self.seconds = seconds
        self.candidate = None
        self.stable = None
        self.changed_at = 0.0
        self.armed = False

    def update(self, pressed, now):
        if pressed != self.candidate:
            self.candidate = pressed
            self.changed_at = now
        if now - self.changed_at < self.seconds or pressed == self.stable:
            return None
        self.stable = pressed
        # 啟動時已按住的按鈕，須先放開，避免誤開始擷取。
        if not self.armed:
            if not pressed:
                self.armed = True
            return None
        return "pressed" if pressed else "released"


class DigitalWorker:
    def __init__(self, settings, lines):
        self.settings = dict(settings)
        self.lines = tuple(lines)
        self.cancel = Event()
        self.alarm = Event()
        self.events = Queue()
        self.thread = Thread(target=self._run, name="ni-digital-io", daemon=False)

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            import nidaqmx
            from nidaqmx.constants import LineGrouping
            with ExitStack() as stack:
                di = do = None
                if self.settings["trigger_mode"] or self.settings["do_channel"]:
                    di = stack.enter_context(nidaqmx.Task())
                    di.di_channels.add_di_chan(self.settings["di_channel"],
                                               line_grouping=LineGrouping.CHAN_PER_LINE)
                    di.start()
                if self.settings["do_channel"]:
                    do = stack.enter_context(nidaqmx.Task())
                    do.do_channels.add_do_chan(self.settings["do_channel"],
                                               line_grouping=LineGrouping.CHAN_PER_LINE)
                    do.write(False)
                debouncer = ButtonDebouncer()
                output = False
                self.events.put(("ready", ""))
                try:
                    while not self.cancel.is_set():
                        if di is not None:
                            values = di.read(timeout=0.1)
                            if isinstance(values, bool):
                                values = [values]
                            if (not isinstance(values, (list, tuple)) or len(values) != len(self.lines)
                                    or any(type(value) is not bool for value in values)):
                                raise ValueError("數位輸入筆數或格式不正確")
                            selected = (values if self.settings["trigger_line"] == "any"
                                        else [values[self.lines.index(self.settings["trigger_line"])]])
                            pressed = any(value == self.settings["active_high"] for value in selected)
                            event = debouncer.update(pressed, monotonic())
                            if event:
                                if event == "pressed":
                                    self.alarm.clear()
                                self.events.put((event, ""))
                        desired = self.alarm.is_set()
                        if do is not None and desired != output:
                            do.write(desired)
                            output = desired
                        self.cancel.wait(0.01)
                finally:
                    if do is not None:
                        do.write(False)
        except Exception as error:
            code = getattr(error, "error_code", None)
            detail = f"NI 錯誤 {code}" if code is not None else type(error).__name__
            self.events.put(("error", f"數位 I/O 失敗（{detail}），請確認通道、接線及設備占用。"))

    def is_running(self):
        return self.thread.is_alive()

    def shutdown(self):
        self.cancel.set()

    def wait(self):
        if self.thread.ident is not None:
            self.thread.join()
