import pytest

from accession.accession import AccessionWgbs
from accession.analysis import Analysis


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
        mock_accession_wgbs.backend,
        "read_json",
        side_effect=[alignment_qc, average_coverage_qc],
    )
    qc = mock_accession_wgbs.make_gembs_alignment_qc(encode_file_no_qc, gs_file=gsfile)
    assert qc["average_coverage"] == 3.5
    assert qc["general_reads"] == 3000
    assert qc["pct_general_reads"] == 50.0
    assert len(mock_accession_wgbs.get_attachment.mock_calls) == 2
