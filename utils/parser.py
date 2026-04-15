import ast
import logging
import operator
import re
from typing import Dict, Tuple, Optional

from config.config import CURRENCY_ABBREVIATIONS, ALL_CURRENCIES, CURRENCY_SYMBOLS

logger = logging.getLogger(__name__)

_ALL_CURRENCY_PATTERNS = {}
_ALL_CURRENCY_PATTERNS.update(CURRENCY_SYMBOLS)
_ALL_CURRENCY_PATTERNS.update(CURRENCY_ABBREVIATIONS)
_ALL_CURRENCY_PATTERNS.update({k.upper(): k.upper() for k in ALL_CURRENCIES.keys()})

_SORTED_CURRENCY_PATTERNS = sorted(_ALL_CURRENCY_PATTERNS.items(), key=lambda x: len(x[0]), reverse=True)

_REGEX_PARTS = []
for pattern, _ in _SORTED_CURRENCY_PATTERNS:
    starts_with_word = re.match(r'^\w', pattern, re.UNICODE) is not None
    ends_with_word = re.search(r'\w$', pattern, re.UNICODE) is not None
    
    prefix = r'(?<!\w)' if starts_with_word else ''
    suffix = r'(?!\w)' if ends_with_word else ''
    
    _REGEX_PARTS.append(rf'{prefix}{re.escape(pattern.lower())}{suffix}')

_CURRENCY_REGEX = re.compile('|'.join(_REGEX_PARTS), re.IGNORECASE)

_PATTERN_TO_CODE = {p.lower(): c for p, c in _ALL_CURRENCY_PATTERNS.items()}

_SPACE_DIGIT_REGEX = re.compile(r'(\d)\s+(\d)')
_STARTING_NUMBER_REGEX = re.compile(r'^([\d\s,.]+)')

_MULTIPLIERS = {
    'тыс': 1000, 'тысяч': 1000, 'тысячи': 1000, 'тысяча': 1000,
    'млн': 1000000, 'миллион': 1000000, 'миллионов': 1000000, 'миллиона': 1000000,
    'млрд': 1000000000, 'миллиард': 1000000000, 'миллиардов': 1000000000,
    'кк': 1000000, 'лям': 1000000, 'ляма': 1000000, 'лямов': 1000000,
    'к': 1000, 'k': 1000, 'm': 1000000, 'b': 1000000000,
    'thousand': 1000, 'million': 1000000, 'billion': 1000000000
}

_MULTIPLIER_REGEXES = {
    re.compile(rf'(\d+(?:[.,]\d+)?)\s*{txt}\b', re.IGNORECASE): val 
    for txt, val in _MULTIPLIERS.items()
}

_FIND_NUMBERS_REGEX = re.compile(r'[\d\s,\.]+')
_SIMPLE_NUMBER_REGEX = re.compile(r'[^\d.]')

_URL_REGEX = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)


def smart_number_parse(text: str) -> str:
    text = _SPACE_DIGIT_REGEX.sub(r'\1\2', text)
    
    number_match = _STARTING_NUMBER_REGEX.match(text)
    if not number_match:
        return text
    
    number_str = number_match.group(1).strip()
    
    dots = number_str.count('.')
    commas = number_str.count(',')
    
    if dots == 0 and commas == 0:
        return number_str
    
    elif dots == 1 and commas == 0:
        return number_str
    
    elif dots == 0 and commas == 1:
        parts = number_str.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            return number_str.replace(',', '.')
        else:
            return number_str.replace(',', '')
    
    elif dots > 0 and commas > 0:
        last_dot = number_str.rfind('.')
        last_comma = number_str.rfind(',')
        
        if last_comma > last_dot:
            return number_str.replace('.', '').replace(',', '.')
        else:
            return number_str.replace(',', '')
    
    elif commas > 1:
        return number_str.replace(',', '')
    
    elif dots > 1:
        return number_str.replace('.', '')
    
    return number_str


def parse_mathematical_expression(expr: str) -> Optional[float]:
    ops = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
    }
    
    def _safe_eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        elif isinstance(node, ast.BinOp) and type(node.op) in ops:
            left = _safe_eval(node.left)
            right = _safe_eval(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ValueError("Division by zero")
            return ops[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_safe_eval(node.operand)
        raise ValueError("Unsafe expression")

    try:
        expr = expr.replace('х', '*').replace('×', '*')
        expr = expr.replace('÷', '/').replace(':', '/')
        expr = expr.replace(' ', '')
        
        allowed_chars = '0123456789+-*/().'
        if not all(c in allowed_chars for c in expr):
            return None
        
        tree = ast.parse(expr, mode='eval')
        return _safe_eval(tree.body)
    except Exception:
        return None


def parse_amount_and_currency(text: str) -> Tuple[Optional[float], Optional[str]]:
    if not text:
        return None, None

    text = _URL_REGEX.sub('', text)
    if not text:
        return None, None

    text = text.strip()
    
    text_lower = text.lower()
    
    currency = None
    currency_match = None
    
    match = _CURRENCY_REGEX.search(text_lower)
    if match:
        matched_text = match.group(0)
        currency = _PATTERN_TO_CODE.get(matched_text.lower())
        currency_match = match
        
    if not currency:
        return None, None
    
    amount_text = _CURRENCY_REGEX.sub('', text_lower)
    amount_text = amount_text.strip()
    
    math_operators = ['+', '-', '*', '/', '(', ')', '^', 'х', '×', '÷', ':']
    has_math = any(op in amount_text for op in math_operators)
    
    if has_math:
        result = parse_mathematical_expression(amount_text)
        if result is not None:
            return result, currency
    
    for pattern, mult_value in _MULTIPLIER_REGEXES.items():
        match = pattern.search(amount_text)
        if match:
            base_number = smart_number_parse(match.group(1))
            try:
                amount = float(base_number) * mult_value
                return amount, currency
            except (ValueError, TypeError) as e:
                logger.debug(f"Failed to parse multiplier number '{match.group(1)}': {e}")
                pass
    
    number_matches = _FIND_NUMBERS_REGEX.findall(amount_text)
    
    for number_str in number_matches:
        cleaned_number = smart_number_parse(number_str)
        try:
            amount = float(cleaned_number)
            if amount >= 0:
                return amount, currency
        except (ValueError, TypeError):
            continue
    
    try:
        simple_number = _SIMPLE_NUMBER_REGEX.sub('', amount_text)
        if simple_number:
            amount = float(simple_number)
            if amount >= 0:
                return amount, currency
    except (ValueError, TypeError):
        pass
    
    return None, None
