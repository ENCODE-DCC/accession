import json
from contextlib import suppress as does_not_raise
from io import StringIO

import pytest

from accession.metadata import (
    CaperMetadata,
    FileMetadata,
    metadata_factory,
    parse_metadata_list,
)


@pytest.fixture
def file_metadata(mocker, wdl_workflow):
    metadata = {
        "foo": "bar",
        "id": "foo",
        "labels": {"caper-backend": "Local"},
        "submittedFiles": {"workflow": wdl_workflow},
    }
    mocker.patch("builtins.open", mocker.mock_open(read_data=json.dumps(metadata)))
    file_metadata = FileMetadata("foo")
    return file_metadata


def test_metadata_backend_name(file_metadata):
    assert file_metadata.backend_name == "Local"


@pytest.mark.parametrize(
    "prefix,expected", [("", "foo_metadata.json"), ("cool", "cool_foo_metadata.json")]
)
def test_metadata_get_filename(file_metadata, prefix, expected):
    result = file_metadata.get_filename(prefix=prefix)
    assert result == expected


def test_metadata_get_as_attachment(file_metadata):
    result = file_metadata.get_as_attachment(filename_prefix="foo")
    assert isinstance(result.contents, bytes)
    assert result.filename.startswith("foo")
    assert result.mime_type == "application/json"


def test_metadata_get_parsed_workflow(file_metadata):
    result = file_metadata.get_parsed_workflow()
    assert result.workflow.meta["version"] == "v1.2.3"


def test_file_metadata(file_metadata):
    assert file_metadata.content["id"] == "foo"
    assert file_metadata.content["foo"] == "bar"


@pytest.mark.parametrize(
    "condition,returned,expected",
    [
        (does_not_raise(), [{"foo": "bar"}], {"foo": "bar"}),
        (pytest.raises(ValueError), [], {}),
    ],
)
def test_caper_metadata(mocker, condition, returned, expected):
    caper_metadata = CaperMetadata("foo")
    mocker.patch.object(caper_metadata.caper_helper, "metadata", return_value=returned)
    with condition:
        result = caper_metadata.content
        assert result == expected


def test_metadata_factory_file_metadata(tmp_path):
    metadata_file = tmp_path / "metadata.json"
    metadata_file.touch()
    result = metadata_factory(str(metadata_file))
    assert isinstance(result, FileMetadata)


def test_metadata_factory_caper_metadata(mocker):
    """
    Note we need to patch in `accession.metadata` and not `accession.caper_helper`. See
    https://docs.python.org/3/library/unittest.mock.html#where-to-patch
    """
    mocker.patch("accession.metadata.caper_conf_exists", return_value=True)
    result = metadata_factory("foo")
    assert isinstance(result, CaperMetadata)


def test_parse_metadata_list():
    metadata_list = StringIO("   foo   \n\n\tbar")
    result = parse_metadata_list(metadata_list)
    assert result == ["foo", "bar"]


def test_parse_metadata_list_invalid_list_raises():
    metadata_list = StringIO("foo\tbar\n")
    with pytest.raises(ValueError):
        parse_metadata_list(metadata_list)


def test_parse_metadata_list_empty_list_raises():
    metadata_list = StringIO("\t\n\n\n\t\t  \n")
    with pytest.raises(ValueError):
        parse_metadata_list(metadata_list)
