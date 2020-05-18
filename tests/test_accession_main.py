import os

import pytest

from accession.__main__ import check_or_set_lab_award, get_parser


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


def test_parser():
    parser = get_parser()
    args = parser.parse_args(["-s", "foo.com", "-m", "meta.json", "-p", "mirna"])
    assert args.server == "foo.com"
