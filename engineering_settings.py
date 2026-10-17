"""工程參數的預設值與 USB-6211 通道檢查。"""

import re
from copy import deepcopy

from daq_acquisition import AcquisitionError, validate_settings


ENGINEERING_DEFAULTS = {
    "trigger_mode": 0,
    "di_channel": "Dev1/port0/line0:3",
    "trigger_line": "any",
    "active_high": True,
    "do_channel": "",
    "model_path": "",
}


def apply_engineering_defaults(config):
    config = deepcopy(config)
    block = config.get("engineering", {})
    if isinstance(block, dict):
        config["engineering"] = {**ENGINEERING_DEFAULTS, **block}
    return config


def validate_engineering(config):
    settings = validate_settings(config.get("daq", {}))
    block = config.get("engineering", {})
    if not isinstance(block, dict):
        raise AcquisitionError("工程設定必須為 JSON 物件。")
    block = {**ENGINEERING_DEFAULTS, **block}
    mode = block["trigger_mode"]
    if type(mode) is not int or mode not in (0, 1, 2):
        raise AcquisitionError("觸發模式必須為 0、1 或 2。")
    device = settings["channel"].split("/")[0]
    match = re.fullmatch(re.escape(device) + r"/port0/line([0-3])(?::([0-3]))?", block["di_channel"])
    if not match or (match[2] is not None and int(match[2]) < int(match[1])):
        raise AcquisitionError("USB-6211 數位輸入須為同一裝置的 port0/line0～3，可設定連續範圍。")
    lines = list(range(int(match[1]), int(match[2] or match[1]) + 1))
    if mode or block["do_channel"]:
        line = block["trigger_line"]
        if (line != "any" and (type(line) is not int or line not in lines)) or type(block["active_high"]) is not bool:
            raise AcquisitionError("請先在工程設定選定按鈕的觸發線與按下有效電位。")
    if block["do_channel"] and not re.fullmatch(
            re.escape(device) + r"/port1/line[0-3]", block["do_channel"]):
        raise AcquisitionError("USB-6211 數位輸出須為同一裝置的 port1/line0～3；空白代表停用。")
    return block, lines
