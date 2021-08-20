import argparse
import os

import pytest

from accession.__main__ import (
    check_or_set_lab_award,
    get_metadatas_from_args,
    get_parser,
)


@pytest.mark.parametrize("lab,award", [("foo", None), (None, "foo")])
def test_check_or_set_lab_award_raises(mocker, lab, award):
    mocker.patch.dict(os.environ, {})
    with pytest.raises(OSError):
        check_or_set_lab_award(lab, award)


@pytest.mark.parametrize(
    "lab,award,environ_prop,expected",
    [
        (None, "bar", "DCC_LAB", ("baz", "bar")),
        ("foo", None, "DCC_AWARD", ("foo", "baz")),
        ("foo", "bar", None, ("foo", "bar")),
    ],
)
def test_check_or_set_lab_award_from_envrion(
    mocker, lab, award, environ_prop, expected
):
    if environ_prop:
        mocker.patch.dict(os.environ, {environ_prop: "baz"})
    result = check_or_set_lab_award(lab, award)
    assert result == expected


def test_get_metadatas_from_args_accession_metadata():
    args = argparse.Namespace(accession_metadata="foo", metadata_list=None)
    result = get_metadatas_from_args(args)
    assert result == ["foo"]


def test_get_metadatas_from_args_metadata_list(mocker):
    mocker.patch("builtins.open")
    mocker.patch("accession.__main__.parse_metadata_list", return_value=["foo", "bar"])
    args = argparse.Namespace(accession_metadata=None, metadata_list="foo")
    result = get_metadatas_from_args(args)
    assert result == ["foo", "bar"]


def test_parser():
    parser = get_parser()
    args = parser.parse_args(["-s", "foo.com", "-m", "meta.json", "-p", "mirna"])
    assert args.server == "foo.com"


def test_parser_info_subcommand_no_args_provided_is_valid():
    parser = get_parser()
    result = parser.parse_args(["info"])
    assert result.ids is None
    assert result.date is None


def test_parser_info_subcommand_date_range_escape():
    parser = get_parser()
    args = parser.parse_args(["info", "-d", "\\-6/24"])
    assert args.ids is None


def test_parser_info_subcommand_multiple_ids():
    parser = get_parser()
    args = parser.parse_args(["info", "-i", "ENCSR123ABC", "21345", "my-wf"])
    assert args.ids == ["ENCSR123ABC", "21345", "my-wf"]


def test_parser_info_subcommand_bare_ids_flag_should_fail():
    parser = get_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["info", "-i"])
