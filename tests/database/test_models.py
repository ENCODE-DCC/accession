from accession.database.models import QualityMetric, RunStatus, WorkflowLabel


def test_run_status_str():
    assert str(RunStatus.Succeeded) == "succeeded"


def test_workflow_label_str():
    assert repr(WorkflowLabel(key="foo", value="bar")) == "bar"


def test_quality_metric_repr():
    assert repr(QualityMetric(portal_at_id="foo")) == "foo"
