from typing import Any, List


def string_to_number(string):
    if not isinstance(string, str):
        return string
    try:
        return int(string)
    except Exception:
        try:
            return float(string)
        except Exception:
            return string


def flatten(nested_input: List[Any]):
    """Flattens a nested list.
    Args:
        input_list: A (possibly) nested list.
    Returns:
        A flattened list, preserving order.
    """

    if not nested_input:
        return []
    if isinstance(nested_input[0], list):
        return flatten(nested_input[0]) + flatten(nested_input[1:])
    else:
        return nested_input[:1] + flatten(nested_input[1:])
