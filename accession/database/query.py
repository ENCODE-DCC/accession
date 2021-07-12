import datetime
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Query, Session

from accession.database.connection import DbSession
from accession.database.models import Run, WorkflowLabel


class DbQuery:
    def __init__(self, session: DbSession):
        self._session = session

    @property
    def session(self) -> Session:
        """
        Avoids an extra indirection by forwarding the session so we don't have to do
        `self.session.session.foo()` every time
        """
        return self._session.session

    def get_runs_by_experiment_at_id(self, experiment_at_id: str) -> Query:
        results = self.session.query(Run).filter_by(experiment_at_id=experiment_at_id)
        return results

    def get_runs_by_workflow_id(self, workflow_id: str) -> Query:
        results = self.session.query(Run).filter_by(workflow_id=workflow_id)
        return results

    def get_runs_by_workflow_label(self, key: str, value: str) -> Query:
        """
        Workflow labels are key-value pairs. The most common form this takes is
        ("caper-str-label", "VALUE"). Rather than overload this function we assume we
        have already determined if the label is a `caper-str-label` label or not
        """
        results = (
            self.session.query(Run)
            .join(WorkflowLabel)
            .filter(and_(WorkflowLabel.key == key, WorkflowLabel.value == value))
        )
        return results

    def get_runs_by_date_range(
        self, start: Optional[datetime.date] = None, end: Optional[datetime.date] = None
    ) -> Query:
        """
        Search for runs between the specified start and end time, inclusive of
        endpoints. If `start` is not specified, will search from the beginning of time,
        and if `end` is not specified then will search to the end of time.
        """
        results = self.filter_results_by_date_range(self.session.query(Run), start, end)
        return results

    def get_all_runs(self) -> Query:
        return self.session.query(Run)

    @staticmethod
    def filter_results_by_date_range(
        results: Query,
        start: Optional[datetime.date] = None,
        end: Optional[datetime.date] = None,
    ) -> Query:
        if start is None:
            start = datetime.date.min
        if end is None:
            end = datetime.date.max
        if start > end:
            raise ValueError("Start time must be less than end")
        filtered = results.filter(Run.date_created >= start).filter(
            Run.date_created <= end
        )
        return filtered
