import datetime
from contextlib import suppress as does_not_raise

import pytest

from accession.database.models import (
    DbFile,
    QualityMetric,
    Run,
    RunStatus,
    WorkflowLabel,
)
from accession.encode_models import FileStatus
from accession.subcommands.info import (
    CromwellWorkflowLabel,
    ExperimentId,
    FillStrategy,
    WorkflowId,
    expand_row,
    get_rows_from_runs,
    make_queries,
    parse_date,
    parse_date_range,
    parse_id,
    parse_ids,
    print_rows,
)


def test_workflow_id_from_string_valid_workflow_id():
    workflow_id = "60fb02a7-31ae-4e9e-8e77-9c2722189cb4"
    result = WorkflowId.from_string(workflow_id)
    assert result.workflow_id == workflow_id


def test_workflow_id_from_string_invalid_workflow_id_returns_none():
    workflow_id = "foo"
    result = WorkflowId.from_string(workflow_id)
    assert result is None


def test_workflow_label_from_string():
    label = "key=value"
    result = CromwellWorkflowLabel.from_string(label)
    assert result.key == "key"
    assert result.value == "value"


def test_workflow_label_from_string_with_escaped_equals_in_key():
    label = "k\\=ey=value"
    result = CromwellWorkflowLabel.from_string(label)
    assert result.key == "k\\=ey"
    assert result.value == "value"


def test_workflow_label_from_string_no_key():
    label = "val\\=ue"
    result = CromwellWorkflowLabel.from_string(label)
    assert result.key == "caper-str-label"
    assert result.value == "val\\=ue"


def test_workflow_label_from_string_multiple_equals_raises():
    label = "key=val=valu\\=e"
    with pytest.raises(ValueError):
        CromwellWorkflowLabel.from_string(label)


@pytest.mark.parametrize(
    "experiment_id",
    ["ENCSR123ABC", "/experiments/ENCSR123ABC/", "experiments/ENCSR123ABC"],
)
def test_experiment_id_from_string(experiment_id):
    result = ExperimentId.from_string(experiment_id)
    assert result.experiment_id == "/experiments/ENCSR123ABC/"


def test_experiment_id_from_string_invalid_returns_none():
    result = ExperimentId.from_string("foo")
    assert result is None


def test_make_queries_labels_and_date_range(db_query, run, additional_runs):
    results = make_queries(
        db_query,
        ids=["foo=bar", "60fb02a7-31ae-4e9e-8e77-9c2722189cb4", "ENCSR123ABC"],
        date_range="3/10/20-3/11/20",
    )
    assert len(results) == 2


def test_make_queries_labels_no_date_range(db_query, run, additional_runs):
    results = make_queries(
        db_query, ids=["foo=bar", "60fb02a7-31ae-4e9e-8e77-9c2722189cb4", "ENCSR123ABC"]
    )
    assert len(results) == 3


def test_make_queries_no_labels_date_range(db_query, run, additional_runs):
    results = make_queries(db_query, date_range="3/11/20")
    assert len(results) == 1


def test_parse_ids():
    ids = ["ENCSR123ABC", "key=value", "60fb02a7-31ae-4e9e-8e77-9c2722189cb4"]
    result = parse_ids(ids)
    assert isinstance(result[0], ExperimentId)
    assert isinstance(result[1], CromwellWorkflowLabel)
    assert isinstance(result[2], WorkflowId)


def test_parse_id_workflow_id():
    workflow_id = "60fb02a7-31ae-4e9e-8e77-9c2722189cb4"
    result = parse_id(workflow_id)
    assert isinstance(result, WorkflowId)


def test_parse_id_experiment_id():
    experiment_id = "ENCSR123ABC"
    result = parse_id(experiment_id)
    assert isinstance(result, ExperimentId)


def test_parse_id_workflow_label():
    workflow_label = "label"
    result = parse_id(workflow_label)
    assert isinstance(result, CromwellWorkflowLabel)


def test_parse_date_range_no_start(mocker):
    m = mocker.MagicMock()
    mocker.patch("accession.subcommands.info.parse_date", m)
    start, _ = parse_date_range("\\-3/4/57")
    assert start is None
    m.assert_called_once_with("3/4/57", fill_strategy=FillStrategy.Max)


def test_parse_date_range_no_end(mocker):
    m = mocker.MagicMock()
    mocker.patch("accession.subcommands.info.parse_date", m)
    _, end = parse_date_range("3/4/57-")
    assert end is None
    m.assert_called_once_with("3/4/57")


def test_parse_date_range(mocker):
    m = mocker.MagicMock(side_effect=(3, 4))
    mocker.patch("accession.subcommands.info.parse_date", m)
    parse_date_range("3/4/57-3/5/57")
    m.assert_has_calls(
        [mocker.call("3/4/57"), mocker.call("3/5/57", fill_strategy=FillStrategy.Max)]
    )


def test_parse_date_range_start_greater_than_end_raises(mocker):
    """
    The side effect here determines the fake values of start and end that we "parse" out
    """
    m = mocker.MagicMock(side_effect=(4, 3))
    mocker.patch("accession.subcommands.info.parse_date", m)
    with pytest.raises(ValueError):
        parse_date_range("3/5/57-3/4/57")


@pytest.mark.parametrize(
    "condition,date,expected",
    [
        (does_not_raise(), "4", datetime.date(2020, month=4, day=1)),
        (does_not_raise(), "4/5", datetime.date(2020, month=4, day=5)),
        (does_not_raise(), "04/05", datetime.date(2020, month=4, day=5)),
        (does_not_raise(), "4/5/19", datetime.date(2019, month=4, day=5)),
        (does_not_raise(), "4/5/1919", datetime.date(1919, month=4, day=5)),
        (pytest.raises(ValueError), "4/5/", None),
        (pytest.raises(ValueError), "today", None),
    ],
)
def test_parse_date(mocker, condition, date, expected):
    mocker.patch(
        "accession.subcommands.info.get_today", return_value=datetime.date(2020, 6, 7)
    )
    with condition:
        result = parse_date(date)
        assert result == expected


def test_parse_date_fillstrategy_max(mocker):
    """
    April always has 30 days, so this is OK.
    """
    mocker.patch(
        "accession.subcommands.info.get_today", return_value=datetime.date(2020, 6, 7)
    )
    result = parse_date("4", fill_strategy=FillStrategy.Max)
    assert result == datetime.date(2020, month=4, day=30)


@pytest.mark.parametrize(
    "input,expected",
    [
        ([1, [2, 3]], [[1, 2], ["", 3]]),
        ([1, [[2, 3], [4, 5]]], [[1, [2, 3]], ["", [4, 5]]]),
    ],
)
def test_expand_row(input, expected):
    result = expand_row(input)
    assert result == expected


def test_get_rows_from_runs():
    run = Run(
        experiment_at_id="foo",
        workflow_id="123",
        date_created=datetime.date(1999, 9, 9),
        status=RunStatus.Succeeded,
        workflow_labels=[WorkflowLabel(key="foo", value="bar")],
        files=[
            DbFile(
                portal_at_id="baz",
                status=FileStatus.Released,
                quality_metrics=[QualityMetric(portal_at_id="qux")],
            ),
            DbFile(portal_at_id="quux", status=FileStatus.Released, quality_metrics=[]),
        ],
    )
    runs = [run]
    result = get_rows_from_runs(runs)
    assert result == [
        ["foo", "123", "bar", "succeeded", "09/09/99", "baz", "released", "qux"],
        ["", "", "", "", "", "quux", "released", ""],
    ]


def test_print_rows(capsys):
    print_rows([["foo", "bar"], ["baz", "qux"]])
    captured = capsys.readouterr()
    assert captured.out == "foo\tbar\nbaz\tqux\n"
