import calendar
import csv
import datetime
import re
import sys
from abc import ABC, abstractclassmethod, abstractmethod
from enum import Enum, auto
from itertools import zip_longest
from typing import List, Optional, Sequence, Tuple, Type, TypeVar, Union

from sqlalchemy.orm import Query

from accession.database.models import Run
from accession.database.query import DbQuery
from accession.helpers import flatten

# Kind of ugly, see https://stackoverflow.com/a/44644576/13501789
_WorkflowId = TypeVar("_WorkflowId", bound="WorkflowId")
_CromwellWorkflowLabel = TypeVar(
    "_CromwellWorkflowLabel", bound="CromwellWorkflowLabel"
)
_ExperimentId = TypeVar("_ExperimentId", bound="ExperimentId")

# Validate dates in month/day/year form, where month & day are either one or two digits
# and year is either two or four digits
DATE_REGEX = r"^(?P<month>\d{1,2})(\/(?P<day>\d{1,2}))?(\/(?P<year>\d{2}|\d{4}))?$"

# Assume we will only accesion things in the 21st century
CURRENT_CENTURY_PREFIX = "20"


class AbstractId(ABC):
    @abstractclassmethod
    def from_string(cls, id: str) -> "Optional[AbstractId]":
        raise NotImplementedError

    @abstractmethod
    def get_query(self, db_query: DbQuery) -> Query:
        raise NotImplementedError


class WorkflowId(AbstractId):
    REGEX = r"^[a-f\d]{8}-([a-f\d]{4}-){3}[a-f\d]{12}$"

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id

    @classmethod
    def from_string(cls: Type[_WorkflowId], workflow_id: str) -> Optional[_WorkflowId]:
        """
        Tries to parse the provided string into a `WorkflowId` and returns it, otherwise
        if it cannot be parsd returns `None`.
        """
        result = re.match(cls.REGEX, workflow_id)
        if result is not None:
            return cls(workflow_id)
        return None

    def get_query(self, db_query: DbQuery) -> Query:
        return db_query.get_runs_by_workflow_id(self.workflow_id)


class CromwellWorkflowLabel(AbstractId):
    """
    Represents a Cromwell workflow label (key value pair). "Cromwell" is in the name to
    avoid potential aliasing with `accession.database.models.WorkflowLabel`
    """

    CAPER_STR_LABEL = "caper-str-label"

    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value

    @classmethod
    def from_string(
        cls: Type[_CromwellWorkflowLabel], workflow_label: str
    ) -> _CromwellWorkflowLabel:
        """
        If given a key=value pair extracts the key and value, otherwise uses
        `cls.CAPER_STR_LABEL` as the key and uses everything else as the value.

        `=` is valid in keys or values, users need to escape any `=` that in the key or
        value with a backslash so that they don't get split on. Here we check that there
        is only one non-escaped equals sign, and raise an error if that is not the case.

        Unlike the other classes `WorkflowId` and `ExperimentId`, this will not return
        `None`, since almost any string will be considered as valid here.
        """
        count_equals = workflow_label.count("=")
        count_escaped_equals = workflow_label.count("\\=")

        if count_equals - count_escaped_equals == 0:
            return cls(cls.CAPER_STR_LABEL, workflow_label)

        if count_equals - count_escaped_equals != 1:
            raise ValueError(
                "Found more than one unescaped `=` in key=value pair, must only '"
                "specify one so parsing is not ambiguous"
            )

        for i, char in enumerate(workflow_label):
            if char == "=":
                if workflow_label[i - 1] != "\\":
                    key, value = workflow_label[0:i], workflow_label[i + 1 :]
                    return cls(key, value)

        # Can skip coverage here, we know the loop above always executes on a string
        # with one non-escaped equals sign in it
        raise ValueError("Could not detect key-value pair")  # pragma: no cover

    def get_query(self, db_query: DbQuery) -> Query:
        return db_query.get_runs_by_workflow_label(key=self.key, value=self.value)


class ExperimentId(AbstractId):
    REGEX = r"^(\/?experiments\/)?(?P<accession>ENCSR\d{3}[A-Z]{3})\/?$"

    def __init__(self, experiment_accession: str) -> None:
        self.experiment_id = f"/experiments/{experiment_accession}/"

    @classmethod
    def from_string(
        cls: Type[_ExperimentId], experiment_id: str
    ) -> Optional[_ExperimentId]:
        """
        Tries to parse the provided string into a `WorkflowId` and returns it, otherwise
        if it cannot be parsed returns `None`.
        """
        result = re.match(cls.REGEX, experiment_id)
        if result is not None:
            return cls(result.group("accession"))
        return None

    def get_query(self, db_query: DbQuery) -> Query:
        return db_query.get_runs_by_experiment_at_id(self.experiment_id)


class FillStrategy(Enum):
    """
    Helper enum that controls how ambiguous day ranges in dates are resolved
    """

    Min = auto()
    Max = auto()


def info(
    db_query: DbQuery, ids: Optional[List[str]] = None, date_range: Optional[str] = None
) -> None:
    """
    The main driver for the subcommand, organizing input parsing, querying the DB, and
    printing the results.
    """
    results = make_queries(db_query, ids, date_range)
    rows = get_rows_from_runs(results)
    rows = add_header_to_rows(rows)
    print_rows(rows)


def make_queries(
    db_query: DbQuery, ids: Optional[List[str]] = None, date_range: Optional[str] = None
) -> List[Run]:
    """
    Transforms user parameters into queries, executes them with additional filtering and
    aggregation, and returns the query results.
    """
    if ids is not None and ids:
        parsed_ids = parse_ids(ids)
        queries = [i.get_query(db_query) for i in parsed_ids]
        if len(queries) > 1:
            query_union = queries[0].union(*queries[1:])
        else:
            query_union = queries[0]
    else:
        query_union = db_query.get_all_runs()

    if date_range is not None:
        start, end = parse_date_range(date_range)
        filtered = DbQuery.filter_results_by_date_range(query_union, start, end)
        return filtered.all()
    else:
        return query_union.all()


def parse_ids(
    ids: List[str]
) -> List[Union[WorkflowId, CromwellWorkflowLabel, ExperimentId]]:
    """
    Simple wrapper to parse each id in the list into the appropriate type
    """
    return [parse_id(i) for i in ids]


def parse_id(id: str) -> Union[WorkflowId, CromwellWorkflowLabel, ExperimentId]:
    """
    First we try to parse as a workflow ID, since this is the most specific and has a
    known regex pattern. Then we try to parse as an experiment accession or `@id`, which
    also has a known pattern but is less general. Failing both, we interpret as a string
    label, since this can be a nearly arbitrary string, which only succeeds or raises.
    """
    workflow_id = WorkflowId.from_string(id)
    if workflow_id is not None:
        return workflow_id
    experiment_id = ExperimentId.from_string(id)
    if experiment_id is not None:
        return experiment_id
    workflow_label = CromwellWorkflowLabel.from_string(id)
    return workflow_label


def parse_date_range(
    date_range: str
) -> Tuple[Optional[datetime.date], Optional[datetime.date]]:
    """
    Returns a (start, end) tuple. If a bare date is specified, i.e. no dashes, then
    returns the same date for start and end if the day of the month is provided, or if
    the day of the month is not provided then will return a range spanning the entire
    month. If a leading `\\-` is specified, then returns `None` as the start. If a
    trailing `-` is specified, then `None` is returned as the end.

    Specifying two or more dashes anywhere in the pattern will raise a ValueError.
    Specifying a range that resolves in such a manner that start > end will also result
    in a ValueError.
    """
    date_range = date_range.lstrip("\\")
    split = date_range.split("-")
    if len(split) > 2:
        raise ValueError(
            "Invalid date range, should only specify one dash in date range string."
        )
    if len(split) == 1:
        date = split[0]
        return parse_date(date), parse_date(date, fill_strategy=FillStrategy.Max)
    if not split[0]:
        start = None
    else:
        start = parse_date(split[0])
    if not split[1]:
        end = None
    else:
        end = parse_date(split[1], fill_strategy=FillStrategy.Max)
    if start is not None and end is not None:
        if start > end:
            raise ValueError("Start date must be less than or equal to end date.")
    return (start, end)


def parse_date(
    date: str, fill_strategy: FillStrategy = FillStrategy.Min
) -> datetime.date:
    """
    Parses date string according to regex. The regex is such that we always recieve a
    month if the string validates. If year is not specified then we use the current
    year. If we don't recieve a day then we choose either the first day of the month
    if the fill_strategy is FillStrategy.Min, or the last day of the month if using
    FillStrategy.Max.
    """
    parsed = re.match(DATE_REGEX, date)
    if parsed is None:
        raise ValueError(f"Could not parse date {date}")

    month = int(parsed.group("month"))

    parsed_year = parsed.group("year")
    if parsed_year is None:
        year = get_today().year
    elif len(parsed_year) == 2:
        year = int(CURRENT_CENTURY_PREFIX + parsed_year)
    else:
        year = int(parsed_year)

    parsed_day = parsed.group("day")
    if parsed_day is None:
        if fill_strategy == FillStrategy.Min:
            # The first day of the month is always 1
            day = 1
        elif fill_strategy == FillStrategy.Max:
            _, day = calendar.monthrange(year, month)
    else:
        day = int(parsed_day)

    return datetime.date(month=month, day=day, year=year)


def get_today() -> datetime.date:
    """
    Keep as separate user defined function to make mocking parse_date easier. See
    https://nedbatchelder.com/blog/201209/mocking_datetimetoday.html
    """
    return datetime.date.today()


def expand_row(
    row: Sequence[Union[str, Sequence[Union[str, Sequence[str]]]]]
) -> List[List[str]]:
    """
    Converts a row with lists as elements into multiple rows with empty strings
    inserted to make column widths more consistent when eventually printing. This is
    easiest to explain visually. A list like `["foo", ["bar", "baz"]]` would be turned
    into `[["foo", "bar"], ["", "baz"]]`. This is used to align the files in the run
    tables.

    See https://mypy.readthedocs.io/en/latest/common_issues.html#invariance-vs-covariance
    for details on why we need Sequence in the signature.
    """
    elems_as_lists = []
    for elem in row:
        if isinstance(elem, list):
            elems_as_lists.append(elem)
        else:
            elems_as_lists.append([elem])
    aligned = [list(i) for i in zip_longest(*elems_as_lists, fillvalue="")]
    return aligned


def get_rows_from_runs(runs: List[Run]) -> List[List[str]]:
    """
    We don't recursively flatten the quality metrics list for each file, otherwise the
    table would take up a lot of vertical space than necessary.
    """
    rows: List[List[str]] = []
    for run in runs:
        run_files = [
            [file.portal_at_id, str(file.status), str(file.quality_metrics).strip("[]")]
            for file in run.files
        ]
        formatted = expand_row(
            [
                run.experiment_at_id,
                run.workflow_id,
                str(run.workflow_labels).strip("[]"),
                str(run.status),
                run.date_created.strftime("%m/%d/%y"),
                run_files,
            ]
        )
        rows.extend(formatted)
    return [flatten(row) for row in rows]


def add_header_to_rows(rows: List[List[str]]) -> List[List[str]]:
    header = [
        [
            "Experiment @id",
            "WF ID",
            "WF Labels",
            "Accessioning Status",
            "Date",
            "File @id",
            "File status",
            "Quality Metrics",
        ]
    ]
    return header + rows


def print_rows(rows: List[List[str]]) -> None:
    """
    Write rows in tabular format to stdout. Unfortunately the `lineterminator` kwarg
    seems to be necessary, otherwise the writer will use `\r\n` for newlines. Since we
    are writing to sys.stdout we can't configure it with the recommended `newline=""` as
    per the `csv` docs.
    """
    writer = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
    for row in rows:
        writer.writerow(row)
