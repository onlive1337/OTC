import os
import re


_CHANGELOG_CACHE = None


def read_changelog():
    global _CHANGELOG_CACHE
    if _CHANGELOG_CACHE is not None:
        return _CHANGELOG_CACHE

    current_file = os.path.abspath(__file__)
    parent_dir = os.path.dirname(os.path.dirname(current_file))
    changelog_path = os.path.join(parent_dir, 'CHANGELOG.md')
    
    try:
        with open(changelog_path, 'r', encoding='utf-8') as file:
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
        return "♾️ Бесконечность"
    
    sign = "-" if number < 0 else ""
    number = abs(number)
    
    if is_original_amount:
        if number == int(number):
            return f"{sign}{int(number):,}".replace(',', ' ')
        else:
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
