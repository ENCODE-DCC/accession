"""
mutate_digits and write_json aren't actually used in the accession module, so they are
not yet tested here. filter_outputs_by_path needs refactoring to be readily testable.
"""
import os

from accession.helpers import filter_outputs_by_path, string_to_number

from .fixtures import MockBlob, MockBucket


def test_filter_outputs_by_path(mock_gc_backend, mocker):
    mocker.patch.object(mock_gc_backend.bucket, "list_blobs", mock_list_blobs)
    filtered = filter_outputs_by_path("gs://my-bucket/three/", backend=mock_gc_backend)
    filtered_paths = [file.path for file in filtered]
    assert filtered_paths == ["three/bazqux.json"]
    os.remove("bazqux.json")


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


def mock_list_blobs():
    mock_bucket = MockBucket("my-bucket")
    for path in ["one/foobar.txt", "three/bazqux.json", "four/spam/eggs.json"]:
        yield MockBlob(path=path, bucket=mock_bucket)
