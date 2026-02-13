import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from utils.utils import (
    parse_amount_and_currency,
    convert_currency,
    format_large_number,
    smart_number_parse,
    parse_mathematical_expression,
)


class TestSmartNumberParse:
    def test_simple_integer(self):
        assert smart_number_parse("1000") == "1000"

    def test_spaces_between_digits(self):
        assert smart_number_parse("10 000") == "10000"

    def test_comma_as_decimal(self):
        assert smart_number_parse("10,50") == "10.50"

    def test_comma_as_thousands(self):
        assert smart_number_parse("10,000") == "10000"

    def test_european_format(self):
        assert smart_number_parse("1.000,50") == "1000.50"

    def test_us_format(self):
        assert smart_number_parse("1,000.50") == "1000.50"

    def test_multiple_commas(self):
        assert smart_number_parse("1,000,000") == "1000000"

    def test_multiple_dots(self):
        assert smart_number_parse("1.000.000") == "1000000"

    def test_single_dot_decimal(self):
        assert smart_number_parse("3.14") == "3.14"


class TestParseMathExpression:
    def test_addition(self):
        assert parse_mathematical_expression("2+3") == 5.0

    def test_multiplication(self):
        assert parse_mathematical_expression("10*5") == 50.0

    def test_division(self):
        assert parse_mathematical_expression("100/4") == 25.0

    def test_complex_expression(self):
        result = parse_mathematical_expression("(10+5)*2")
        assert result == 30.0

    def test_division_by_zero(self):
        assert parse_mathematical_expression("5/0") is None

    def test_invalid_chars(self):
        assert parse_mathematical_expression("import os") is None

    def test_cyrillic_multiply(self):
        assert parse_mathematical_expression("5×3") == 15.0

    def test_colon_divide(self):
        assert parse_mathematical_expression("10:2") == 5.0

    def test_empty(self):
        assert parse_mathematical_expression("") is None


class TestParseAmountAndCurrency:
    def test_basic_usd(self):
        amount, currency = parse_amount_and_currency("100 USD")
        assert amount == 100.0
        assert currency == "USD"

    def test_dollar_sign(self):
        amount, currency = parse_amount_and_currency("$50")
        assert amount == 50.0
        assert currency == "USD"

    def test_russian_rubles(self):
        amount, currency = parse_amount_and_currency("1000 рублей")
        assert amount == 1000.0
        assert currency == "RUB"

    def test_euro_symbol(self):
        amount, currency = parse_amount_and_currency("€200")
        assert amount == 200.0
        assert currency == "EUR"

    def test_multiplier_k(self):
        amount, currency = parse_amount_and_currency("5к USD")
        assert amount == 5000.0
        assert currency == "USD"

    def test_multiplier_million(self):
        amount, currency = parse_amount_and_currency("1 млн рублей")
        assert amount == 1000000.0
        assert currency == "RUB"

    def test_crypto_btc(self):
        amount, currency = parse_amount_and_currency("0.5 BTC")
        assert amount == 0.5
        assert currency == "BTC"

    def test_crypto_russian_name(self):
        amount, currency = parse_amount_and_currency("1 биткоин")
        assert amount == 1.0
        assert currency == "BTC"

    def test_empty_string(self):
        amount, currency = parse_amount_and_currency("")
        assert amount is None
        assert currency is None

    def test_no_currency(self):
        amount, currency = parse_amount_and_currency("12345")
        assert amount is None
        assert currency is None

    def test_currency_first(self):
        amount, currency = parse_amount_and_currency("USD 100")
        assert amount == 100.0
        assert currency == "USD"

    def test_comma_number(self):
        amount, currency = parse_amount_and_currency("10,982 KZT")
        assert amount == 10982.0
        assert currency == "KZT"


class TestConvertCurrency:
    RATES = {
        "USD": 1.0,
        "EUR": 0.92,
        "RUB": 92.5,
        "BTC": 1 / 45000,
    }

    def test_usd_to_eur(self):
        result = convert_currency(100, "USD", "EUR", self.RATES)
        assert result == pytest.approx(92.0)

    def test_eur_to_usd(self):
        result = convert_currency(92, "EUR", "USD", self.RATES)
        assert result == pytest.approx(100.0)

    def test_rub_to_eur(self):
        result = convert_currency(9250, "RUB", "EUR", self.RATES)
        assert result == pytest.approx(92.0)

    def test_usd_to_usd(self):
        result = convert_currency(100, "USD", "USD", self.RATES)
        assert result == pytest.approx(100.0)

    def test_missing_from_currency(self):
        with pytest.raises(KeyError):
            convert_currency(100, "GBP", "USD", self.RATES)

    def test_missing_to_currency(self):
        with pytest.raises(KeyError):
            convert_currency(100, "USD", "GBP", self.RATES)

    def test_zero_rate_protection(self):
        rates_with_zero = {"USD": 1.0, "BAD": 0}
        with pytest.raises(ValueError):
            convert_currency(100, "BAD", "USD", rates_with_zero)

    def test_zero_to_rate_protection(self):
        rates_with_zero = {"USD": 1.0, "BAD": 0}
        with pytest.raises(ValueError):
            convert_currency(100, "USD", "BAD", rates_with_zero)


class TestFormatLargeNumber:
    def test_zero(self):
        assert format_large_number(0) == "0"

    def test_small_fiat(self):
        assert format_large_number(1234.56) == "1,234.56"

    def test_very_small(self):
        result = format_large_number(0.005)
        assert "0.005" in result

    def test_crypto_small(self):
        result = format_large_number(0.00012345, is_crypto=True)
        assert "0.0001234" in result

    def test_crypto_large(self):
        result = format_large_number(1500000, is_crypto=True)
        assert "M" in result

    def test_infinity(self):
        result = format_large_number(1e101)
        assert "♾️" in result

    def test_negative(self):
        result = format_large_number(-100)
        assert result.startswith("-")

    def test_original_amount_integer(self):
        result = format_large_number(1000, is_original_amount=True)
        assert result == "1 000"

    def test_original_amount_decimal(self):
        result = format_large_number(1000.5, is_original_amount=True)
        assert "1 000" in result
        assert ".5" in result

    def test_crypto_zero(self):
        result = format_large_number(0, is_crypto=True)
        assert result == "0"

    def test_crypto_tiny(self):
        result = format_large_number(0.000000001, is_crypto=True)
        assert "e" in result.lower()  # научная нотация

    def test_billion(self):
        result = format_large_number(1500000000, is_crypto=True)
        assert "B" in result

