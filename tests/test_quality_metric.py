import pytest

from accession.quality_metric import QualityMetric


def test_quality_metric_no_file_id_raises(payload):
    with pytest.raises(Exception):
        QualityMetric(payload, file_id=None)


def test_quality_metric_init(payload):
    qm = QualityMetric(payload, "my_id")
    assert qm.files == ["my_id"]
    assert qm.payload == payload


@pytest.fixture
def payload():
    return {"foo": "bar"}
