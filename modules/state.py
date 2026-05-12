import json
import os
import threading
import uuid
from copy import deepcopy
from typing import Any

from astrbot.api import logger
from .base import BaseService
from .paths import (
    DATA_DIR,
    STATE_FILE,
    R18_WHITELIST_FILE,
    LAST_ZIP_FILE,
    LAST_ITEMS_FILE,
    TOKEN_STATE_FILE,
)
from .pixiv_utils import read_json


DEFAULT_STATE = {
    "token_state": {},
    "last_items": {},
    "last_zip": {},
    "r18_whitelist": {"qq_list": []},
}

LEGACY_STATE_FILES = {
    "token_state": TOKEN_STATE_FILE,
    "last_items": LAST_ITEMS_FILE,
    "last_zip": LAST_ZIP_FILE,
    "r18_whitelist": R18_WHITELIST_FILE,
}


class StateService(BaseService):
    def __init__(self, plugin):
        super().__init__(plugin)
        self._state_lock = threading.RLock()

    def default_state(self) -> dict:
        return deepcopy(DEFAULT_STATE)

    def normalize_state(self, data: Any) -> dict:
        state = self.default_state()
        if isinstance(data, dict):
            for key, default_value in DEFAULT_STATE.items():
                value = data.get(key)
                state[key] = value if isinstance(value, type(default_value)) else deepcopy(default_value)
        return state

    def read_state(self) -> dict:
        self.migrate_legacy_if_needed()
        data = read_json(STATE_FILE, {})
        return self.normalize_state(data)

    def write_state(self, state: dict):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        state = self.normalize_state(state)
        tmp = STATE_FILE.with_name(f"{STATE_FILE.name}.tmp.{uuid.uuid4().hex}")
        try:
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, STATE_FILE)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            os.chmod(STATE_FILE, 0o600)
        except Exception:
            pass

    def get_section(self, key: str, default=None):
        with self._state_lock:
            state = self.read_state()
            value = state.get(key, default)
            return deepcopy(value)

    def set_section(self, key: str, value):
        with self._state_lock:
            state = self.read_state()
            state[key] = deepcopy(value)
            self.write_state(state)

    def clear_section(self, key: str):
        with self._state_lock:
            state = self.read_state()
            state[key] = deepcopy(DEFAULT_STATE.get(key, {}))
            self.write_state(state)

    def has_section_data(self, key: str) -> bool:
        value = self.get_section(key, DEFAULT_STATE.get(key, {}))
        if isinstance(value, dict):
            return bool(value)
        if isinstance(value, list):
            return bool(value)
        return value is not None

    def migrate_legacy_if_needed(self):
        if STATE_FILE.exists():
            return
        with self._state_lock:
            if STATE_FILE.exists():
                return
            state = self.default_state()
            changed = False
            for key, path in LEGACY_STATE_FILES.items():
                data = read_json(path, None)
                if isinstance(data, dict) and data:
                    state[key] = data
                    changed = True
            if changed:
                self.write_state(state)
                logger.info("Pixivc 已将旧 JSON 状态迁移到 data/state.json。")

    def token_state_exists(self) -> bool:
        data = self.get_section("token_state", {})
        return isinstance(data, dict) and bool(data.get("access_token"))
