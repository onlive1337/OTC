import html
import re
from pathlib import Path
from typing import Iterable, Tuple

from aiogram.types import InputRichMessage

from config.config import ALL_CURRENCIES, MAX_CONVERSION_AMOUNT, MIN_CONVERSION_AMOUNT
from config.languages import LANGUAGES
from utils.rates import convert_currency

FORMAT_PLAIN = "plain"
FORMAT_QUOTE = "quote"
FORMAT_TABLE = "table"
DISPLAY_FORMATS = (FORMAT_PLAIN, FORMAT_QUOTE, FORMAT_TABLE)


def resolve_display_format(use_quote: bool, use_rich: bool) -> str:
    if use_rich:
        return FORMAT_TABLE
    if use_quote:
        return FORMAT_QUOTE
    return FORMAT_PLAIN


def flags_for_display_format(display_format: str) -> tuple[bool, bool]:
    if display_format == FORMAT_PLAIN:
        return False, False
    if display_format == FORMAT_QUOTE:
        return True, False
    if display_format == FORMAT_TABLE:
        return False, True
    raise ValueError(f"Unsupported display format: {display_format!r}")


_CHANGELOG_CACHE = None
_CHANGELOG_MAX_LEN = 4000
_CHANGELOG_TRUNCATE_AT = 3800


def get_currency_symbol(code: str) -> str:
    symbol = ALL_CURRENCIES.get(code, '')
    if not symbol or symbol == code:
        return ''
    return symbol + ' '


def _escape_and_cap_changelog(raw_text: str) -> str:
    escaped = html.escape(raw_text)
    if len(escaped) <= _CHANGELOG_MAX_LEN:
        return escaped
    cutoff = min(len(raw_text), _CHANGELOG_TRUNCATE_AT)
    while cutoff > 0:
        truncated = raw_text[:cutoff].rstrip() + '\n\n...'
        escaped = html.escape(truncated)
        if len(escaped) <= _CHANGELOG_MAX_LEN:
            return escaped
        cutoff = max(0, cutoff - 200)
    return '...'


def read_changelog(changelog_path: Path | None = None) -> str:
    global _CHANGELOG_CACHE
    if changelog_path is None and _CHANGELOG_CACHE is not None:
        return _CHANGELOG_CACHE

    target_path = changelog_path or (Path(__file__).resolve().parent.parent / 'CHANGELOG.md')

    try:
        with target_path.open('r', encoding='utf-8') as file:
            content = file.read()

        versions = re.split(r'(?=^## \[)', content, flags=re.MULTILINE)
        header = versions[0] if versions else ''
        version_blocks = [v for v in versions[1:] if v.strip()]

        if len(version_blocks) > 2:
            raw_result = header + ''.join(version_blocks[:2]).rstrip() + '\n\n---\n_...и ещё старые версии_'
        else:
            raw_result = content

        result = _escape_and_cap_changelog(raw_result)
        if changelog_path is None:
            _CHANGELOG_CACHE = result
        return result
    except FileNotFoundError:
        return "Чейнджлог не найден."


def format_too_large_message(user_lang: str, max_amount: float = MAX_CONVERSION_AMOUNT) -> str:
    formatted_max = format_large_number(max_amount, is_original_amount=True)
    default_msg = f"Number is too large. Max allowed: {formatted_max}"
    template = LANGUAGES[user_lang].get('number_too_large', default_msg)
    if '{max_amount}' in template:
        return template.format(max_amount=formatted_max)
    return template


def format_too_small_message(user_lang: str, min_amount: float = MIN_CONVERSION_AMOUNT) -> str:
    formatted_min = format_large_number(min_amount, is_original_amount=True)
    default_msg = f"Amount is too small. Minimum: {formatted_min}"
    template = LANGUAGES[user_lang].get('number_too_small', default_msg)
    if '{min_amount}' in template:
        return template.format(min_amount=formatted_min)
    return template


def build_math_response(user_lang: str, expression: str, result: float) -> str:
    result_str = format_large_number(result)
    total_len = len(expression) + len(result_str)
    if total_len <= 35:
        template_key = 'math_result_short'
        fallback = '{expression} = <b>{result}</b>'
    else:
        template_key = 'math_result_long'
        fallback = '{expression}\n= <b>{result}</b>'
    return LANGUAGES[user_lang].get(template_key, fallback).format(
        expression=html.escape(expression),
        result=result_str,
    )


def format_large_number(number, is_crypto=False, is_original_amount=False):
    if abs(number) > 1e100:
        return "♾️ Infinity"

    sign = "-" if number < 0 else ""
    number = abs(number)
    
    if is_original_amount:
        if number == int(number):
            return f"{sign}{int(number):,}".replace(',', ' ')
        else:
            if 0 < number < 1e-10:
                tiny = f"{sign}{number:.18f}".rstrip('0').rstrip('.')
                if tiny != f"{sign}0":
                    return tiny
                return f"{sign}{number:.2e}"
            formatted = f"{sign}{number:,.10f}".rstrip('0').rstrip('.')
            parts = formatted.split('.')
            if len(parts) == 2:
                return parts[0].replace(',', ' ') + '.' + parts[1]
            return parts[0].replace(',', ' ')
    
    if is_crypto:
        if number == 0:
            return "0"
        elif number < 0.00000001:
            return f"{sign}{number:.2e}"
        elif number < 0.01:
            return f"{sign}{number:.8f}".rstrip('0').rstrip('.')
        elif number < 1:
            return f"{sign}{number:.6f}".rstrip('0').rstrip('.')
        elif number < 1000:
            return f"{sign}{number:.4f}".rstrip('0').rstrip('.')
        elif number < 1000000:
            return f"{sign}{number:,.2f}"
        elif number < 1000000000:
            return f"{sign}{number/1000000:.3f}M"
        elif number < 1000000000000:
            return f"{sign}{number/1000000000:.3f}B"
        else:
            return f"{sign}{number:.2e}"
    else:
        if number == 0:
            return "0"
        if number < 0.01:
            return f"{sign}{number:.6f}".rstrip('0').rstrip('.')
        if number < 1:
            return f"{sign}{number:.4f}".rstrip('0').rstrip('.')
        return f"{sign}{number:,.2f}"


def _build_rich_table_html(rows: Iterable[Tuple[str, str, str]], user_lang: str) -> str:
    col_currency = html.escape(LANGUAGES[user_lang].get('table_col_currency', 'Currency'))
    col_amount = html.escape(LANGUAGES[user_lang].get('table_col_amount', 'Amount'))
    col_rate = html.escape(LANGUAGES[user_lang].get('table_col_rate', 'Rate'))

    body_rows = []
    for label, amount_str, unit_rate_str in rows:
        body_rows.append(
            f"<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td align=\"right\"><code>{html.escape(amount_str)}</code></td>"
            f"<td align=\"right\">{html.escape(unit_rate_str)}</td>"
            f"</tr>"
        )

    return (
        "<table bordered striped compact>"
        f"<tr><th>{col_currency}</th><th align=\"right\">{col_amount}</th><th align=\"right\">{col_rate}</th></tr>"
        + "".join(body_rows)
        + "</table>"
    )


def _render_conversion_rich_block(
    amount: float,
    from_currency: str,
    fiat_rows: list[Tuple[str, str, str]],
    crypto_rows: list[Tuple[str, str, str]],
    user_lang: str,
    use_quote: bool,
) -> str:
    header_text = f"{format_large_number(amount, is_original_amount=True)} {get_currency_symbol(from_currency)}{from_currency}"
    parts = [f"<h4>{html.escape(header_text)}</h4>"]

    sections = [
        (LANGUAGES[user_lang]['fiat_currencies'].rstrip(':'), fiat_rows, True),
        (LANGUAGES[user_lang]['cryptocurrencies_output'].rstrip(':'), crypto_rows, not fiat_rows),
    ]
    for title, rows, open_by_default in sections:
        if not rows:
            continue
        table_html = _build_rich_table_html(rows, user_lang)
        safe_title = html.escape(title)
        if use_quote:
            open_attr = " open" if open_by_default else ""
            parts.append(f"<details{open_attr}><summary><b>{safe_title}</b></summary>{table_html}</details>")
        else:
            parts.append(f"<p><b>{safe_title}</b></p>{table_html}")

    return "".join(parts)


def build_rich_rows(
    amount: float,
    from_currency: str,
    target_list: list[str],
    rates: dict,
    is_crypto: bool,
) -> list[Tuple[str, str, str]]:
    rows = []
    for to_cur in target_list:
        if to_cur == from_currency:
            continue
        try:
            converted = convert_currency(amount, from_currency, to_cur, rates)
            unit_rate = convert_currency(1.0, from_currency, to_cur, rates)
        except (KeyError, ValueError, OverflowError):
            continue
        rows.append((
            f"{get_currency_symbol(to_cur)}{to_cur}",
            format_large_number(converted, is_crypto),
            format_large_number(unit_rate, is_crypto),
        ))
    return rows


def build_conversion_rich_message(
    amount: float,
    from_currency: str,
    fiat_rows: list[Tuple[str, str, str]],
    crypto_rows: list[Tuple[str, str, str]],
    user_lang: str,
    use_quote: bool,
) -> InputRichMessage:
    """Build a structured Rich Message with currency conversion tables."""
    rich_html = _render_conversion_rich_block(
        amount, from_currency, fiat_rows, crypto_rows, user_lang, use_quote
    )
    return InputRichMessage(html=rich_html, skip_entity_detection=True)


def build_multi_conversion_rich_message(
    items: list[Tuple[float, str, list[Tuple[str, str, str]], list[Tuple[str, str, str]]]],
    user_lang: str,
    use_quote: bool,
) -> InputRichMessage:
    """Build a multi-conversion Rich Message separated by horizontal rules."""
    blocks = [
        _render_conversion_rich_block(amount, from_cur, fiat_rows, crypto_rows, user_lang, use_quote)
        for amount, from_cur, fiat_rows, crypto_rows in items
    ]
    return InputRichMessage(html="<hr/>".join(blocks), skip_entity_detection=True)
