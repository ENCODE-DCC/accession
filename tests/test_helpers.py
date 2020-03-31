from accession.helpers import flatten, string_to_number


def test_string_to_number_not_string_return_input():
    not_string = 3
    result = string_to_number(not_string)
    assert result == not_string


def test_string_to_number_stringy_int_returns_int():
    int_string = "3"
    result = string_to_number(int_string)
    assert isinstance(result, int)
    assert result == 3


def test_string_to_number_stringy_float_returns_float():
    float_string = "3.0"
    result = string_to_number(float_string)
    assert isinstance(result, float)
    assert result == 3.0


def test_string_to_number_non_number_string_returns_input():
    non_number_string = "3.0a"
    result = string_to_number(non_number_string)
    assert result == non_number_string


def test_flatten() -> None:
    result = flatten([["a", "b"], ["c", "d"]])
    assert result == ["a", "b", "c", "d"]
