from contextlib import suppress as does_not_raise

import pytest

from accession.accession_steps import FileParams
from accession.encode_models import (
    EncodeAnalysis,
    EncodeAttachment,
    EncodeCommonMetadata,
    EncodeExperiment,
    EncodeFile,
    EncodeQualityMetric,
    EncodeStepRun,
)


@pytest.fixture(scope="module")
def encode_attachment():
    return EncodeAttachment(
        filename="/my/dir/haz/my_text_file", contents=b"foo bar baz"
    )


@pytest.fixture
def encode_file():
    return EncodeFile(
        {
            "@id": "1",
            "status": "foo",
            "output_type": "reads",
            "dataset": "chip",
            "md5sum": "123",
            "quality_metrics": [{"@type": "Yes"}],
        }
    )


@pytest.fixture(scope="module")
def encode_common_metadata():
    return EncodeCommonMetadata("/labs/lab/", "award")


@pytest.fixture
def encode_analysis():
    return EncodeAnalysis({"files": ["/files/1/", "/files/2/"]})


@pytest.fixture(scope="module")
def encode_experiment():
    properties = {
        "@id": "foo",
        "assay_term_name": "mirna",
        "replicates": [
            {"biological_replicate_number": 1},
            {"biological_replicate_number": 3},
        ],
        "analyses": [{"files": ["/files/1/"]}],
    }
    return EncodeExperiment(properties)


@pytest.fixture
def payload():
    return {"foo": "bar"}


def test_encode_common_metadata_lab_pi(encode_common_metadata):
    assert encode_common_metadata.lab_pi == "lab"


def test_encode_attachment_encode_attachment_data():
    assert EncodeAttachment.encode_attachment_data(b"foo bar baz") == "Zm9vIGJhciBiYXo="


def test_encode_attachment_get_bytes_from_dict():
    assert EncodeAttachment.get_bytes_from_dict({"a": "b"}) == b'{"a": "b"}'


def test_encode_attachment_encode_attachment_data_string_input():
    with pytest.raises(TypeError):
        EncodeAttachment.encode_attachment_data("foo bar baz")


def test_encode_attachment_make_download_link(encode_attachment):
    assert encode_attachment.make_download_link(extension=".txt") == "my_text_file.txt"


def test_encode_attachment_get_portal_object(encode_attachment):
    result = encode_attachment.get_portal_object(
        mime_type="text/plain", extension=".txt"
    )
    assert result == {
        "type": "text/plain",
        "download": "my_text_file.txt",
        "href": "data:text/plain;base64,Zm9vIGJhciBiYXo=",
    }


@pytest.mark.parametrize(
    "other_file,expected",
    [
        (1, False),
        (
            EncodeFile(
                {
                    "@id": "1",
                    "status": "foo",
                    "output_type": "reads",
                    "dataset": "chip",
                    "md5sum": "123",
                    "quality_metrics": [{"@type": "Yes"}],
                }
            ),
            True,
        ),
        (
            EncodeFile(
                {
                    "@id": "1",
                    "status": "foo",
                    "output_type": "reads",
                    "dataset": "atac",
                    "md5sum": "123",
                    "quality_metrics": [{"@type": "Yes"}],
                }
            ),
            False,
        ),
    ],
)
def test_encode_file_eq(encode_file, other_file, expected):
    result = encode_file == other_file
    assert result == expected


def test_encode_file_properties(encode_file):
    assert encode_file.at_id == "1"
    assert encode_file.status == "foo"
    assert encode_file.md5sum == "123"
    assert encode_file.output_type == "reads"
    assert encode_file.dataset == "chip"


@pytest.mark.parametrize("key,expected", [("status", "foo"), ("name", None)])
def test_encode_file_get(encode_file, key, expected):
    assert encode_file.get(key) == expected


@pytest.mark.parametrize(
    "condition,file,expected",
    [
        (does_not_raise(), EncodeFile({"@id": "1", "step_run": "foo"}), "foo"),
        (does_not_raise(), EncodeFile({"@id": "2", "step_run": {"@id": "bar"}}), "bar"),
        (pytest.raises(ValueError), EncodeFile({"@id": "3"}), ""),
    ],
)
def test_encode_file_step_run_id(condition, file, expected):
    with condition:
        assert file.step_run_id == expected


@pytest.mark.parametrize(
    "condition,new_properties",
    [(does_not_raise(), {"@id": "1"}), (pytest.raises(ValueError), {"@id": "new"})],
)
def test_encode_file_portal_file_setter(encode_file, condition, new_properties):
    with condition:
        encode_file.portal_file = new_properties
        assert encode_file.portal_file == new_properties


@pytest.mark.parametrize("qc_type,expected", [("Yes", True), ("No", False)])
def test_encode_file_has_qc(encode_file, qc_type, expected):
    assert encode_file.has_qc(qc_type) == expected


@pytest.mark.parametrize(
    "files,expected",
    [
        (
            [
                EncodeFile({"@id": 1, "status": "foo"}),
                EncodeFile({"@id": 2, "status": "bar"}),
                EncodeFile({"@id": 3, "status": "deleted"}),
            ],
            2,
        ),
        ([EncodeFile({"@id": 1, "status": "foo"})], 1),
    ],
)
def test_encode_file_filter_encode_files_by_status(files, expected):
    assert len(EncodeFile.filter_encode_files_by_status(files)) == expected


def test_encode_file_from_template(encode_common_metadata):
    result = EncodeFile.from_template(
        aliases=["foo"],
        assembly="mm10",
        common_metadata=encode_common_metadata,
        dataset="dataset_id",
        derived_from=["bar"],
        file_params=FileParams(
            {
                "filekey": "foo",
                "file_format": "bam",
                "file_format_type": "bar",
                "output_type": "reads",
                "derived_from_files": [],
            }
        ),
        file_size="123",
        file_md5sum="456",
        step_run_id="step_run_id",
        genome_annotation="V29",
        extras={"extra": "cool"},
    )
    assert result == {
        "_profile": "file",
        "aliases": ["foo"],
        "assembly": "mm10",
        "award": "award",
        "dataset": "dataset_id",
        "derived_from": ["bar"],
        "extra": "cool",
        "file_format": "bam",
        "file_format_type": "bar",
        "file_size": "123",
        "genome_annotation": "V29",
        "lab": "/labs/lab/",
        "md5sum": "456",
        "output_type": "reads",
        "status": "uploading",
        "step_run": "step_run_id",
    }


@pytest.mark.parametrize(
    "other_analysis,expected",
    [
        (EncodeAnalysis({"files": ["/files/2/", "/files/1/"]}), True),
        (EncodeAnalysis({"files": ["/files/1/"]}), False),
        ("foo", False),
    ],
)
def test_encode_analysis_eq(encode_analysis, other_analysis, expected):
    result = encode_analysis == other_analysis
    assert result == expected


def test_encode_analysis_str(encode_analysis):
    assert str(encode_analysis) == "['/files/1/', '/files/2/']"


def test_encode_analysis_files(encode_analysis):
    assert encode_analysis.files == ["/files/1/", "/files/2/"]


def test_encode_analysis_files_setter(encode_analysis):
    encode_analysis.files = ["/files/3/"]
    assert encode_analysis.files == ["/files/3/"]


def test_encode_analysis_from_files(encode_file):
    result = EncodeAnalysis.from_files([encode_file])
    assert result == EncodeAnalysis({"files": ["1"]})


@pytest.mark.parametrize(
    "condition,analysis,expected",
    [
        (does_not_raise(), EncodeAnalysis({"files": ["foo"]}), {"files": ["foo"]}),
        (pytest.raises(ValueError), EncodeAnalysis({}), {}),
    ],
)
def test_encode_analysis_get_portal_object(condition, analysis, expected):
    with condition:
        result = analysis.get_portal_object()
        assert result == expected


def test_encode_experiment_get_number_of_biological_replicates(encode_experiment):
    assert encode_experiment.get_number_of_biological_replicates() == 2


def test_encode_experiment_is_replicated(encode_experiment):
    assert encode_experiment.is_replicated is True


def test_encode_experiment_assay_term_name(encode_experiment):
    assert encode_experiment.assay_term_name == "mirna"


def test_encode_experiment_analyses(encode_experiment):
    result = encode_experiment.analyses
    assert result == [EncodeAnalysis({"files": ["/files/1/"]})]


def test_encode_experiment_make_postable_analyses_from_analysis_payload(
    encode_experiment
):
    result = encode_experiment.make_postable_analyses_from_analysis_payload(
        {"files": ["foo"]}
    )
    assert result == {"analyses": [{"files": ["foo"]}], "_enc_id": "foo"}


def test_encode_quality_metric_no_file_id_raises(payload):
    with pytest.raises(Exception):
        EncodeQualityMetric(payload, file_id=None)


def test_encode_quality_metric_init(payload):
    qm = EncodeQualityMetric(payload, "my_id")
    assert qm.files == ["my_id"]
    assert qm.payload == payload


def test_encode_quality_metric_get_portal_object(payload):
    qm = EncodeQualityMetric(payload, "my_id")
    result = qm.get_portal_object()
    assert result == {
        "foo": "bar",
        "quality_metric_of": ["my_id"],
        "status": "in progress",
    }


def test_encode_step_run_init():
    run = EncodeStepRun({"@id": "1", "name": "foo"})
    assert run.at_id == "1"
