from logging import Logger
from typing import List

import pytest

from accession.encode_models import EncodeFile
from accession.preflight import MatchingMd5Record, PreflightHelper


@pytest.fixture
def preflight_helper(mocker):
    return PreflightHelper(mocker.create_autospec(Logger))


@pytest.mark.parametrize(
    "matches,expected",
    [
        (
            [
                MatchingMd5Record(
                    "gs://foo/a.b",
                    [
                        EncodeFile(
                            {
                                "@id": "/files/ENCFF123ABC/",
                                "status": "released",
                                "dataset": "ENCSRCBA321",
                            }
                        ),
                        EncodeFile(
                            {
                                "@id": "/files/ENCFF456DEF/",
                                "status": "in progress",
                                "dataset": "ENCSRCBA321",
                            }
                        ),
                    ],
                ),
                MatchingMd5Record(
                    "gs://foo/c.d",
                    [
                        EncodeFile(
                            {
                                "@id": "/files/ENCFF000AAA/",
                                "status": "revoked",
                                "dataset": "ENCSR222FOO",
                            }
                        )
                    ],
                ),
            ],
            [
                ("Found files with duplicate md5sums",),
                (
                    "File Path    | Matching Portal Files | Portal Status | Portal File Dataset",
                ),
                (
                    "gs://foo/a.b | ENCFF123ABC           | released      | ENCSRCBA321        ",
                ),
                (
                    "             | ENCFF456DEF           | in progress   | ENCSRCBA321        ",
                ),
                (
                    "gs://foo/c.d | ENCFF000AAA           | revoked       | ENCSR222FOO        ",
                ),
            ],
        ),
        ([], [("No MD5 conflicts found.",)]),
    ],
)
def test_report_dry_run(
    preflight_helper: PreflightHelper,
    matches: List[MatchingMd5Record],
    expected: List[str],
):
    """
    The mocker.patch creates a unittest MagicMock on the logger. We want to conform
    with pytest-style asserts so we manually extract the print args, rather than using
    unittest-style mock.assert_*() methods. The first index of mock_calls extracts the
    matching call (in call order), the second selects the args from the (name, args,
    kwargs) tuple for that call, and the last index selects the positional arg.
    """
    preflight_helper.report_dry_run(matches)
    log_call_args = [
        preflight_helper.logger.info.mock_calls[i][1]  # type: ignore
        for i in range(0, len(expected))
    ]
    assert log_call_args == expected


@pytest.mark.parametrize(
    "matching,expected",
    [
        ([], None),
        (
            [
                EncodeFile(
                    {"@id": "/files/foo/", "status": "released", "dataset": "bar"}
                )
            ],
            MatchingMd5Record(
                "file",
                [
                    EncodeFile(
                        {"@id": "/files/foo/", "status": "released", "dataset": "bar"}
                    )
                ],
            ),
        ),
    ],
)
def test_make_file_matching_md5_record(preflight_helper, matching, expected):
    filename = "file"
    result = preflight_helper.make_file_matching_md5_record(filename, matching)
    assert result == expected


def test_preflight_helper_make_log_messages_from_records(preflight_helper):
    matches = [
        MatchingMd5Record(
            "file",
            [
                EncodeFile(
                    {"@id": "/files/foo/", "status": "released", "dataset": "bar"}
                )
            ],
        )
    ]
    messages = preflight_helper.make_log_messages_from_records(matches)
    assert messages == [
        "File Path | Matching Portal Files | Portal Status | Portal File Dataset",
        "file      | foo                   | released      | bar                ",
    ]
