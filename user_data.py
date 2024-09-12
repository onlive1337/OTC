import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any, List
from config import USER_DATA_FILE, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='logs.txt', filemode='a')
logger = logging.getLogger(__name__)

class UserData:
    def __init__(self):
        self.user_data = self.load_user_data()
        self.chat_data = self.load_chat_data()
        self.bot_launch_date = datetime.now().strftime('%Y-%m-%d')

    def load_chat_data(self):
        try:
            with open('chat_data.json', 'r') as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def initialize_chat_settings(self, chat_id: int):
        if str(chat_id) not in self.chat_data:
            self.chat_data[str(chat_id)] = {
                'currencies': ACTIVE_CURRENCIES[:5],
                'crypto': CRYPTO_CURRENCIES[:5],
                'quote_format': False
            }
            self.save_chat_data()
        logger.info(f"Initialized settings for chat {chat_id}")

    def get_user_quote_format(self, user_id):
        return self.user_data[str(user_id)].get("use_quote_format", True)

    def set_user_quote_format(self, user_id, use_quote):
        self.user_data[str(user_id)]["use_quote_format"] = use_quote
        self.save_user_data()

    def get_chat_quote_format(self, chat_id):
        return self.chat_data.get(str(chat_id), {}).get("use_quote_format", True)

    def set_chat_quote_format(self, chat_id, use_quote):
        if str(chat_id) not in self.chat_data:
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]["use_quote_format"] = use_quote
        self.save_chat_data()

    def save_chat_data(self):
        with open('chat_data.json', 'w') as file:
            json.dump(self.chat_data, file, indent=4)

    def get_chat_currencies(self, chat_id):
        return self.chat_data.get(str(chat_id), {}).get("selected_currencies", ACTIVE_CURRENCIES[:5])

    def set_chat_currencies(self, chat_id, currencies):
        if str(chat_id) not in self.chat_data:
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]["selected_currencies"] = currencies
        self.save_chat_data()

    def get_chat_crypto(self, chat_id):
        return self.chat_data.get(str(chat_id), {}).get("selected_crypto", CRYPTO_CURRENCIES)

    def set_chat_crypto(self, chat_id, crypto_list):
        if str(chat_id) not in self.chat_data:
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]["selected_crypto"] = crypto_list
        self.save_chat_data()

    def load_user_data(self):
        try:
            with open(USER_DATA_FILE, 'r') as file:
                data = json.load(file)
                return defaultdict(lambda: {
                    "interactions": 0,
                    "last_seen": None,
                    "selected_crypto": CRYPTO_CURRENCIES,  
                    "selected_currencies": ACTIVE_CURRENCIES[:5],
                    "language": "ru",
                    "first_seen": self.bot_launch_date,
                    "use_quote_format": True
                }, data)
        except (FileNotFoundError, json.JSONDecodeError):
            return defaultdict(lambda: {
                "interactions": 0,
                "last_seen": None,
                "selected_crypto": CRYPTO_CURRENCIES,  
                "selected_currencies": ACTIVE_CURRENCIES[:5],
                "language": "ru",
                "first_seen": self.bot_launch_date,
                "use_quote_format": True
            })

    def get_user_currencies(self, user_id):
        return self.user_data[str(user_id)].get("selected_currencies", ACTIVE_CURRENCIES[:5])

    def set_user_currencies(self, user_id, currencies):
        self.user_data[str(user_id)]["selected_currencies"] = currencies
        self.save_user_data()

    def save_user_data(self):
        with open(USER_DATA_FILE, 'w') as file:
            json.dump(self.user_data, file, indent=4)

    def update_user_data(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        if str(user_id) not in self.user_data:
            self.user_data[str(user_id)] = {
                "interactions": 0, 
                "last_seen": today, 
                "selected_crypto": CRYPTO_CURRENCIES,
                "selected_currencies": ACTIVE_CURRENCIES[:5],
                "language": "ru",
                "first_seen": today
            }
        self.user_data[str(user_id)]["interactions"] += 1
        self.user_data[str(user_id)]["last_seen"] = today
        self.save_user_data()

    def get_user_crypto(self, user_id: int) -> List[str]:
        user_id_str = str(user_id)
        if user_id_str not in self.user_data or "selected_crypto" not in self.user_data[user_id_str]:
            self.user_data[user_id_str]["selected_crypto"] = CRYPTO_CURRENCIES
        return self.user_data[user_id_str]["selected_crypto"]

    def set_user_crypto(self, user_id: int, crypto_list: List[str]):
        self.user_data[str(user_id)]["selected_crypto"] = crypto_list
        self.save_user_data()

    def get_statistics(self):
        today = datetime.now().strftime('%Y-%m-%d')
        total_users = len(self.user_data)
        active_today = sum(1 for user in self.user_data.values() if user['last_seen'] == today)
        new_today = sum(1 for user in self.user_data.values() if user['first_seen'] == today)

        return {
            "total_users": total_users,
            "active_today": active_today,
            "new_today": new_today
        }
    
    def get_user_language(self, user_id):
        return self.user_data[str(user_id)].get("language", "ru")
    
    def set_user_language(self, user_id, language):
        self.user_data[str(user_id)]["language"] = language
        self.save_user_data()