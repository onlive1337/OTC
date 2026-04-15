import re
from pathlib import Path

from config.config import ALL_CURRENCIES


_CHANGELOG_CACHE = None


def get_currency_symbol(code: str) -> str:
    symbol = ALL_CURRENCIES.get(code, '')
    if not symbol or symbol == code:
        return ''
    return symbol + ' '


def read_changelog():
    global _CHANGELOG_CACHE
    if _CHANGELOG_CACHE is not None:
        return _CHANGELOG_CACHE

    changelog_path = Path(__file__).resolve().parent.parent / 'CHANGELOG.md'

    try:
        with changelog_path.open('r', encoding='utf-8') as file:
            content = file.read()
        
        versions = re.split(r'(?=^## \[)', content, flags=re.MULTILINE)
        header = versions[0] if versions else ''
        version_blocks = [v for v in versions[1:] if v.strip()]
        
        if len(version_blocks) > 2:
            result = header + ''.join(version_blocks[:2]).rstrip()
            result += '\n\n---\n_...и ещё старые версии_'
            _CHANGELOG_CACHE = result
            return result
            
        _CHANGELOG_CACHE = content
        return content
    except FileNotFoundError:
        return "Чейнджлог не найден."


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
