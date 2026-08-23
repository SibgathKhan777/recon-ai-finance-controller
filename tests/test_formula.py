import pytest

from recon.formula import FormulaError, evaluate

ROW = {"amount": 1000.0, "fee": 8.0, "tax": 2.0}


def test_simple_subtraction():
    assert evaluate("amount - fee - tax", ROW) == 990.0


def test_multiplication_and_precedence():
    assert evaluate("fee + tax * 2", ROW) == 12.0


def test_division():
    assert evaluate("amount / 2", ROW) == 500.0


def test_parentheses():
    assert evaluate("(amount - fee) / 2", ROW) == 496.0


def test_unary_minus():
    assert evaluate("-fee", ROW) == -8.0


def test_unknown_field_rejected():
    with pytest.raises(FormulaError):
        evaluate("amount - bogus_field", ROW)


def test_missing_field_on_row_rejected():
    with pytest.raises(FormulaError):
        evaluate("ledger_amount - fee", ROW)


def test_function_call_rejected():
    with pytest.raises(FormulaError):
        evaluate("__import__('os').system('echo pwned')", ROW)


def test_attribute_access_rejected():
    with pytest.raises(FormulaError):
        evaluate("amount.__class__", ROW)


def test_string_literal_rejected():
    with pytest.raises(FormulaError):
        evaluate("'amount'", ROW)


def test_garbage_syntax_rejected():
    with pytest.raises(FormulaError):
        evaluate("amount - - -", ROW)
