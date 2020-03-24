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


def flatten(nested_list):
    if isinstance(nested_list, str):
        yield nested_list
    if isinstance(nested_list, list):
        for item in nested_list:
            yield from flatten(item)
