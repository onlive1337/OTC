import re
import zlib

import ujson
from aiogram.types import InputRichMessage

from config.config import ALL_CURRENCIES
from utils.formatter import build_conversion_rich_message, build_multi_conversion_rich_message
from utils.widget import WIDGET_HTML, build_widget_caption, build_widget_state


def test_widget_html_respects_telegram_limits_and_profile():
    raw = WIDGET_HTML.encode('utf-8')
    compressed = zlib.compress(raw, 9)

    assert len(raw) <= 32768
    assert len(compressed) <= 4096
    assert '\x00' not in WIDGET_HTML
    assert re.search(r'<\s*(input|select|textarea|form|label)\b', WIDGET_HTML, re.IGNORECASE) is None
    assert 'vh' not in re.findall(r'\b\d+vh\b', WIDGET_HTML)


def test_widget_state_stays_under_1024_bytes():
    all_rates = {code: 1.5 for code in ALL_CURRENCIES}
    state_raw = build_widget_state(
        all_rates,
        list(ALL_CURRENCIES.keys()),
        ['BTC', 'ETH', 'USDT'],
        'ru',
    )
    assert len(state_raw.encode('utf-8')) <= 1024
    parsed = ujson.loads(state_raw)
    assert parsed['l'] == 'ru'
    assert parsed['f'] == 'USD'
    assert 'USD' in parsed['r']
    assert build_widget_caption('ru')


def test_rich_conversion_builders_escape_and_render_tables():
    msg = build_conversion_rich_message(
        100.0,
        'USD',
        [('🇪🇺 EUR', '90.00', '0.90')],
        [('₿ BTC', '0.001', '0.00001')],
        'ru',
        use_quote=True,
    )
    assert isinstance(msg, InputRichMessage)
    assert msg.html is not None
    assert '<table bordered striped compact>' in msg.html
    assert '<details open>' in msg.html
    assert '🇪🇺 EUR' in msg.html
    assert '0.001' in msg.html

    multi = build_multi_conversion_rich_message(
        [
            (100.0, 'USD', [('🇪🇺 EUR', '90.00', '0.90')], []),
            (50.0, 'EUR', [('🇺🇸 USD', '55.56', '1.11')], []),
        ],
        'en',
        use_quote=False,
    )
    assert multi.html is not None
    assert '<hr/>' in multi.html
    assert '<details' not in multi.html
