import pytest

from accession.accession import AccessionBulkRna


def test_get_bytes_from_dict():
    assert AccessionBulkRna.get_bytes_from_dict({"a": "b"}) == b'{"a": "b"}'
