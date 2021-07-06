import pytest
from pytest_mock import MockerFixture

from accession.accession import AccessionWgbs
from accession.analysis import Analysis
from accession.helpers import Recorder


@pytest.fixture
def mock_accession_wgbs(
    mocker,
    mock_accession_gc_backend,
    mock_metadata,
    mock_accession_steps,
    server_name,
    common_metadata,
    gsfile,
):
    mocked_accession = AccessionWgbs(
        mock_accession_steps,
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        server_name,
        common_metadata,
        Recorder(use_in_memory_db=True),
        no_log_file=True,
    )
    mocker.patch.object(mocked_accession.analysis, "get_files", return_value=[gsfile])
    mocker.patch.object(mocked_accession.analysis, "search_down", return_value=[gsfile])
    mocker.patch.object(mocked_accession, "queue_qc", lambda output, *_: output)
    mocker.patch.object(mocked_accession, "get_attachment")
    return mocked_accession


def test_accession_wgbs_make_gembs_alignment_qc(
    mocker, mock_accession_wgbs, gsfile, encode_file_no_qc
):
    alignment_qc = {"general_reads": 3000, "pct_general_reads": 0.5}
    average_coverage_qc = {"average_coverage": {"average_coverage": 3.5}}
    mocker.patch.object(
        gsfile, "read_json", side_effect=[alignment_qc, average_coverage_qc]
    )
    qc = mock_accession_wgbs.make_gembs_alignment_qc(encode_file_no_qc, file=gsfile)
    assert qc["average_coverage"] == 3.5
    assert qc["general_reads"] == 3000
    assert qc["pct_general_reads"] == 50.0
    assert len(mock_accession_wgbs.get_attachment.mock_calls) == 2


def test_accession_wgbs_get_preferred_default_qc_value(
    mocker: MockerFixture, mock_accession_wgbs, gsfile
):
    mocker.patch.object(mock_accession_wgbs.analysis, "search_up")
    mocker.patch.object(gsfile, "read_json", return_value={"general_reads": 30})
    mocker.patch.object(
        mock_accession_wgbs.analysis, "search_down", return_value=[gsfile]
    )
    result = mock_accession_wgbs.get_preferred_default_qc_value(gsfile)
    mock_accession_wgbs.analysis.search_up.assert_called_once()
    assert result == 30


@pytest.mark.parametrize(
    "qc_value,current_best_qc_value,expected", [(10.0, 1.0, True), (3.0, 10.0, False)]
)
def test_accession_wgbs_preferred_default_should_be_updated(
    mock_accession_wgbs, qc_value, current_best_qc_value, expected
):
    result = mock_accession_wgbs.preferred_default_should_be_updated(
        qc_value, current_best_qc_value
    )
    assert result is expected
