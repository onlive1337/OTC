import os
import sys
import tempfile
from pathlib import Path

# Offline tests must never pick up production credentials or open the live DB.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TELEGRAM_BOT_TOKEN'] = '123456:offline-test-token'
os.environ['LOG_CHAT_ID'] = ''
os.environ['COINCAP_API_KEY'] = ''
os.environ['COINGECKO_DEMO_API_KEY'] = ''
_test_storage = tempfile.TemporaryDirectory(prefix='otc-tests-')
os.environ['DB_PATH'] = str(Path(_test_storage.name) / 'test.db')
