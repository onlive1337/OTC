import json
import os
import tempfile
from datetime import datetime
from typing import List
import logging
import portalocker
from config.config import USER_DATA_FILE, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES, CHAT_DATA_FILE

logger = logging.getLogger(__name__)

class UserData:
    def __init__(self):
        self.user_data = self.load_user_data()
        self.chat_data = self.load_chat_data()
        self.bot_launch_date = datetime.now().strftime('%Y-%m-%d')

    def _atomic_write(self, path: str, data: dict):
        dir_name = os.path.dirname(path) or '.'
        with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False) as tf:
            json.dump(data, tf, indent=4)
            tmp_name = tf.name
        os.replace(tmp_name, path)

    def _locked_load(self, path: str):
        try:
            with open(path, 'r') as f:
                portalocker.lock(f, portalocker.LOCK_SH)
                try:
                    return json.load(f)
                finally:
                    portalocker.unlock(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def load_user_data(self):
        return self._locked_load(USER_DATA_FILE)

    def load_chat_data(self):
        return self._locked_load(CHAT_DATA_FILE)

    def save_user_data(self):
        self._atomic_write(USER_DATA_FILE, self.user_data)

    def save_chat_data(self):
        self._atomic_write(CHAT_DATA_FILE, self.chat_data)

    def reload_data(self):
        self.user_data = self.load_user_data()
        self.chat_data = self.load_chat_data()

    def get_user_data(self, user_id):
        user_id_str = str(user_id)
        self.reload_data()
        if user_id_str not in self.user_data:
            self.user_data[user_id_str] = self.initialize_user_data(user_id)
            self.save_user_data()
        return self.user_data[user_id_str]

    def get_chat_data(self, chat_id):
        chat_id_str = str(chat_id)
        self.reload_data()
        if chat_id_str not in self.chat_data:
            self.initialize_chat_settings(chat_id)
        return self.chat_data[chat_id_str]

    def initialize_user_data(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        
        default_lang = "ru" if user_id > 0 else "en"
        
        return {
            "interactions": 0,
            "last_seen": today,
            "selected_currencies": ACTIVE_CURRENCIES[:5],
            "selected_crypto": CRYPTO_CURRENCIES[:5], 
            "language": default_lang,
            "first_seen": today,
            "use_quote_format": True
        }

    def initialize_chat_settings(self, chat_id: int):
        if str(chat_id) not in self.chat_data:
            self.chat_data[str(chat_id)] = {
                'currencies': ACTIVE_CURRENCIES[:5],
                'crypto': CRYPTO_CURRENCIES[:5],
                'quote_format': False
            }
            self.save_chat_data()
        logger.info(f"Initialized settings for chat {chat_id}")

    def update_user_data(self, user_id):
        user_data = self.get_user_data(user_id)
        user_data["interactions"] += 1
        user_data["last_seen"] = datetime.now().strftime('%Y-%m-%d')
        self.save_user_data()

    def update_chat_cache(self, chat_id: int):
        chat_id_str = str(chat_id)
        self.reload_data()
        if chat_id_str not in self.chat_data:
            self.initialize_chat_settings(chat_id)
        logger.info(f"Updated chat cache for chat {chat_id}")

    def get_user_currencies(self, user_id):
        return self.get_user_data(user_id).get("selected_currencies", ACTIVE_CURRENCIES[:5])

    def set_user_currencies(self, user_id, currencies):
        user_data = self.get_user_data(user_id)
        user_data["selected_currencies"] = currencies
        self.save_user_data()

    def get_user_crypto(self, user_id: int) -> List[str]:
        return self.get_user_data(user_id).get("selected_crypto", CRYPTO_CURRENCIES)

    def set_user_crypto(self, user_id: int, crypto_list: List[str]):
        user_data = self.get_user_data(user_id)
        user_data["selected_crypto"] = crypto_list
        self.save_user_data()

    def get_user_language(self, user_id):
        return self.get_user_data(user_id).get("language", "en")
    
    def set_user_language(self, user_id, language):
        user_data = self.get_user_data(user_id)
        user_data["language"] = language
        self.save_user_data()

    def get_user_quote_format(self, user_id):
        return self.get_user_data(user_id).get("use_quote_format", True)

    def set_user_quote_format(self, user_id, use_quote):
        user_data = self.get_user_data(user_id)
        user_data["use_quote_format"] = use_quote
        self.save_user_data()

    def get_chat_quote_format(self, chat_id):
        return self.get_chat_data(chat_id).get("quote_format", False)

    def set_chat_quote_format(self, chat_id, use_quote):
        chat_data = self.get_chat_data(chat_id)
        chat_data["quote_format"] = use_quote
        self.save_chat_data()

    def get_chat_currencies(self, chat_id):
        return self.get_chat_data(chat_id).get("currencies", ACTIVE_CURRENCIES[:5])

    def set_chat_currencies(self, chat_id, currencies):
        chat_data = self.get_chat_data(chat_id)
        chat_data["currencies"] = currencies
        self.save_chat_data()

    def get_chat_crypto(self, chat_id):
        return self.get_chat_data(chat_id).get("crypto", CRYPTO_CURRENCIES[:5])

    def set_chat_crypto(self, chat_id, crypto_list):
        chat_data = self.get_chat_data(chat_id)
        chat_data["crypto"] = crypto_list
        self.save_chat_data()

    def get_statistics(self):
        self.reload_data()
        today = datetime.now().strftime('%Y-%m-%d')
        total_users = len(self.user_data)
        active_today = sum(1 for user in self.user_data.values() if user['last_seen'] == today)
        new_today = sum(1 for user in self.user_data.values() if user['first_seen'] == today)

        return {
            "total_users": total_users,
            "active_today": active_today,
            "new_today": new_today
        }