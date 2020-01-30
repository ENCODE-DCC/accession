from contextlib import contextmanager

import pytest

from accession.accession import AccessionChip
from accession.file import GSFile
from accession.task import Task


@pytest.fixture
def gsfile():
    task = {
        "inputs": {
            "prefix": "pooled-pr1_vs_pooled-pr2",
            "fastqs_R1": ["gs://abc/spam.fastq.gz"],
        },
        "outputs": {},
    }
    my_task = Task("my_task", task, analysis="qux")
    return GSFile(
        "foo", "gs://abc/spam.fastq.gz", md5sum="123", size="456", task=my_task
    )


@contextmanager
def does_not_raise():
    """
    A dummy context manager useful for parametrized tests that may or may not raise
    an error. Usage of this expectation indicates that the current test parameter set
    should not raise an error.

    See http://doc.pytest.org/en/latest/example/parametrize.html#parametrizing-conditional-raising
    """
    yield


REP = "rep1"


@pytest.fixture
def mock_accession_patched_qc(mocker, mock_accession_chip, gsfile):
    """
    Performs shared patches to qc metric maker functions. Dependents on this fixture
    should patch mock_accession_chip.backend.read_json() to supply the appropriate qc stub
    """
    mocker.patch.object(mock_accession_chip, "file_has_qc", return_value=False)
    mocker.patch.object(
        mock_accession_chip.analysis, "get_files", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip, "get_chip_pipeline_replicate", return_value=REP
    )
    mocker.patch.object(mock_accession_chip, "queue_qc", lambda output, *args: output)
    return mock_accession_chip


"""
Ideally these would be pytest fixtures, but they don't play nicely when passed as
return_value in mocker.patch.object.
"""
align_qc_dup = {
    "align": {
        "samstat": {
            "rep1": {
                "total_reads": 31167664,
                "total_reads_qc_failed": 0,
                "duplicate_reads": 0,
                "duplicate_reads_qc_failed": 0,
                "mapped_reads": 28618875,
                "mapped_reads_qc_failed": 0,
                "pct_mapped_reads": 91.8,
                "paired_reads": 0,
                "paired_reads_qc_failed": 0,
                "read1": 0,
                "read1_qc_failed": 0,
                "read2": 0,
                "read2_qc_failed": 0,
                "properly_paired_reads": 0,
                "properly_paired_reads_qc_failed": 0,
                "pct_properly_paired_reads": 0.0,
                "with_itself": 0,
                "with_itself_qc_failed": 0,
                "singletons": 0,
                "singletons_qc_failed": 0,
                "pct_singletons": 0.0,
                "diff_chroms": 0,
                "diff_chroms_qc_failed": 0,
            }
        }
    }
}


align_qc_nodup = {
    "align": {
        "nodup_samstat": {
            "rep1": {
                "total_reads": 22033059,
                "total_reads_qc_failed": 0,
                "duplicate_reads": 0,
                "duplicate_reads_qc_failed": 0,
                "mapped_reads": 22033059,
                "mapped_reads_qc_failed": 0,
                "pct_mapped_reads": 100.0,
                "paired_reads": 0,
                "paired_reads_qc_failed": 0,
                "read1": 0,
                "read1_qc_failed": 0,
                "read2": 0,
                "read2_qc_failed": 0,
                "properly_paired_reads": 0,
                "properly_paired_reads_qc_failed": 0,
                "pct_properly_paired_reads": 0.0,
                "with_itself": 0,
                "with_itself_qc_failed": 0,
                "singletons": 0,
                "singletons_qc_failed": 0,
                "pct_singletons": 0.0,
                "diff_chroms": 0,
                "diff_chroms_qc_failed": 0,
            }
        }
    }
}


align_enrich_qc = {
    "align_enrich": {
        "xcor_score": {
            "rep1": {
                "subsampled_reads": 15000000,
                "estimated_fragment_len": 100,
                "corr_estimated_fragment_len": 0.215460537129363,
                "phantom_peak": 80,
                "corr_phantom_peak": 0.2136902,
                "argmin_corr": 1500,
                "min_corr": 0.1630407,
                "NSC": 1.321514,
                "RSC": 1.034953,
            }
        },
        "jsd": {
            "rep1": {
                "auc": 0.22069022540637373,
                "syn_auc": 0.49477458966709664,
                "x_intercept": 0.1425972317467426,
                "syn_x_intercept": 0.0,
                "elbow_pt": 0.6535464871014113,
                "syn_elbow_pt": 0.506542601727043,
                "jsd": 0.003923754877223693,
                "syn_jsd": 0.3758404209038387,
                "pct_genome_enrich": 28.538239921946694,
                "diff_enrich": 0.31028662370578,
                "ch_div": 0.002800808043644715,
            }
        },
    }
}


library_qc = {
    "align": {
        "dup": {
            "rep1": {
                "unpaired_reads": 0,
                "paired_reads": 31681025,
                "unmapped_reads": 0,
                "unpaired_duplicate_reads": 0,
                "paired_duplicate_reads": 1669558,
                "paired_optical_duplicate_reads": 32245,
                "pct_duplicate_reads": 5.269900000000001,
            }
        }
    },
    "lib_complexity": {
        "lib_complexity": {
            "rep1": {
                "total_fragments": 31665818,
                "distinct_fragments": 29998922,
                "positions_with_one_read": 1523995,
                "NRF": 0.94736,
                "PBC1": 0.946871,
                "PBC2": 18.638593,
            }
        }
    },
}


tf_replication_qc = {
    "general": {"pipeline_type": "tf"},
    "replication": {
        "reproducibility": {
            "idr": {
                "Nt": 26692,
                "N1": 27036,
                "N2": 11788,
                "Np": 31098,
                "N_opt": 31098,
                "N_consv": 26692,
                "opt_set": "pooled-pr1_vs_pooled-pr2",
                "consv_set": "rep1_vs_rep2",
                "rescue_ratio": 1.1650681852240372,
                "self_consistency_ratio": 2.2935188327112317,
                "reproducibility": "borderline",
            }
        }
    },
}


histone_replication_qc = {
    "general": {"pipeline_type": "histone"},
    "replication": {
        "reproducibility": {
            "overlap": {
                **tf_replication_qc["replication"]["reproducibility"][  # type: ignore
                    "idr"
                ]  # type: ignore
            }
        }
    },
}


peak_enrichment_qc = {
    "general": {"pipeline_type": "tf"},
    "replication": {
        "reproducibility": {"idr": {"opt_set": "pooled-pr1_vs_pooled-pr2"}}
    },
    "peak_stat": {
        "peak_region_size": {
            "idr_opt": {
                "min_size": 140.0,
                "25_pct": 385.0,
                "50_pct": 560.0,
                "75_pct": 560.0,
                "max_size": 2298.0,
                "mean": 482.61428387677665,
            }
        }
    },
    "peak_enrich": {
        "frac_reads_in_peaks": {
            "idr": {
                "rep1_vs_rep2": {"frip": 0.06048766636136033},
                "pooled-pr1_vs_pooled-pr2": {"frip": 0.06720758657484392},
            }
        }
    },
}


@pytest.mark.parametrize(
    "pipeline_type,expected", [("tf", "idr"), ("histone", "overlap")]
)
def test_get_chip_pipeline_replication_method(pipeline_type, expected):
    method = AccessionChip.get_chip_pipeline_replication_method(
        {"general": {"pipeline_type": pipeline_type}}
    )
    assert method == expected


@pytest.mark.parametrize(
    "qc,expected",
    [
        (
            b'{"replication": {"reproducibility": {"idr": {"opt_set": "pooled-pr1_vs_pooled-pr2"}}}}',
            {"preferred_default": True},
        ),
        (
            b'{"replication": {"reproducibility": {"idr": {"opt_set": "rep1_vs_rep2"}}}}',
            {},
        ),
    ],
)
def test_maybe_preferred_default(mocker, mock_accession_chip, gsfile, qc, expected):
    mocker.patch.object(
        mock_accession_chip.analysis, "get_files", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip.analysis.backend, "read_file", return_value=qc
    )
    result = mock_accession_chip.maybe_preferred_default(gsfile)
    assert result == expected


@pytest.mark.parametrize(
    "log_contents,expectation,expected_value",
    [(b"42", does_not_raise(), 42), (b"foo", pytest.raises(RuntimeError), 42)],
)
def test_add_chip_mapped_read_length(
    mocker, mock_accession_chip, gsfile, log_contents, expectation, expected_value
):
    mocker.patch.object(
        mock_accession_chip.analysis, "search_up", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip.analysis.backend, "read_file", return_value=log_contents
    )
    with expectation:
        result = mock_accession_chip.add_mapped_read_length(gsfile)
        assert result == {"mapped_read_length": expected_value}


@pytest.mark.parametrize(
    "processing_stage,align_qc",
    [("unfiltered", align_qc_dup), ("filtered", align_qc_nodup)],
)
def test_make_chip_alignment_qc(
    mocker, mock_accession_patched_qc, gsfile, processing_stage, align_qc
):
    mocker.patch.object(
        mock_accession_patched_qc.backend, "read_json", return_value=align_qc
    )
    output_type = "alignments"
    qc_key = "nodup_samstat"
    if processing_stage == "unfiltered":
        output_type = " ".join([processing_stage, output_type])
        qc_key = "samstat"
    encode_file = {"output_type": output_type}
    qc = mock_accession_patched_qc.make_chip_alignment_qc(encode_file, gs_file="foo")
    for k, v in qc.items():
        if k == "processing_stage":
            assert v == processing_stage
        else:
            assert v == align_qc["align"][qc_key][REP][k]


@pytest.fixture
def mock_accession_align_enrich(mocker, mock_accession_patched_qc, gsfile):
    mocker.patch.object(
        mock_accession_patched_qc.analysis, "search_up", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_patched_qc.analysis, "search_down", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_patched_qc.backend, "read_file", return_value=b"foo"
    )
    return mock_accession_patched_qc


def test_make_chip_align_enrich_qc(mocker, mock_accession_align_enrich, gsfile):
    mocker.patch.object(
        mock_accession_align_enrich.backend, "read_json", return_value=align_enrich_qc
    )
    task = {"inputs": {"fastqs_R1": ["gs://abc/spam.fastq.gz"]}, "outputs": {}}
    stub_task = Task("align_R1", task, analysis="qux")
    mocker.patch.object(
        mock_accession_align_enrich.analysis, "get_tasks", return_value=[stub_task]
    )
    encode_file = {}
    qc = mock_accession_align_enrich.make_chip_align_enrich_qc(
        encode_file, gs_file=gsfile
    )
    keys = ["xcor_score", "jsd"]
    for key in keys:
        for k, v in align_enrich_qc["align_enrich"][key][REP].items():
            assert qc[k] == v
    for key in ["cross_correlation_plot", "jsd_plot", "gc_bias_plot"]:
        for prop in ["type", "download", "href"]:
            assert prop in qc[key]


def test_make_chip_align_enrich_qc_raises(mocker, mock_accession_align_enrich, gsfile):
    mocker.patch.object(
        mock_accession_align_enrich.analysis, "get_tasks", return_value=[]
    )
    with pytest.raises(ValueError):
        mock_accession_align_enrich.make_chip_align_enrich_qc({}, gs_file=gsfile)


def test_make_chip_library_qc(mocker, mock_accession_patched_qc, gsfile):
    mocker.patch.object(
        mock_accession_patched_qc.backend, "read_json", return_value=library_qc
    )
    qc = mock_accession_patched_qc.make_chip_library_qc({}, gs_file="foo")
    for k, v in library_qc["align"]["dup"][REP].items():
        assert qc[k] == v
    for k, v in library_qc["lib_complexity"]["lib_complexity"][REP].items():
        assert qc[k] == v


def test_get_chip_pipeline_replicate(mocker, mock_accession_chip, gsfile):
    mocker.patch.object(
        mock_accession_chip.analysis, "search_up", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip.analysis,
        "metadata",
        {"inputs": {"fastqs_rep1_R1": ["gs://abc/spam.fastq.gz"]}},
    )
    rep = mock_accession_chip.get_chip_pipeline_replicate(gsfile)
    assert rep == "rep1"


def test_get_chip_pipeline_replicate_raises(mocker, mock_accession_chip, gsfile):
    mocker.patch.object(
        mock_accession_chip.analysis, "search_up", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip.analysis,
        "metadata",
        {"inputs": {"fastqs_rep1_R1": ["gs://abc/eggs.fastq.gz"]}},
    )
    with pytest.raises(ValueError):
        mock_accession_chip.get_chip_pipeline_replicate(gsfile)


@pytest.mark.parametrize(
    "task_name,current_set,reproducible_peaks_source",
    [
        ("idr_ppr", "pooled-pr1_vs_pooled-pr2", "Np"),
        ("idr", "rep1_vs_rep2", "Nt"),
        ("idr_pr", "rep1-pr1_vs_rep1-pr2", "N1"),
        ("overlap_ppr", "pooled-pr1_vs_pooled-pr2", "Np"),
        ("overlap", "rep1_vs_rep2", "Nt"),
        ("overlap_pr", "rep1-pr1_vs_rep1-pr2", "N1"),
    ],
)
def test_make_chip_replication_qc(
    mocker, mock_accession_patched_qc, task_name, current_set, reproducible_peaks_source
):
    """
    Tests 3 cases each for histone and TF pipelines. Histone QC shouldn't have IDR
    properties (plot, log, and cutoff). For both, only the optimal set should specify
    rescue ratio, self-consistency ratio, and reproducibility (pass/fail).
    """
    pipeline_qc = histone_replication_qc
    method = "overlap"
    if task_name.startswith("idr"):
        pipeline_qc = tf_replication_qc
        method = "idr"
    mocker.patch.object(
        mock_accession_patched_qc.backend, "read_json", return_value=pipeline_qc
    )
    mocker.patch.object(
        mock_accession_patched_qc.backend, "read_file", return_value=b"foo"
    )
    if method == "idr":
        idr_thresh = 0.05
        task = {
            "inputs": {"prefix": current_set, "idr_thresh": idr_thresh},
            "outputs": {"idr_log": "gs://abc/idr.log", "idr_plot": "gs://abc/plot.png"},
        }
    else:
        task = {"inputs": {"prefix": current_set}, "outputs": []}
    my_task = Task(task_name, task, analysis="qux")
    gsfile = GSFile(
        "foo", "gs://abc/spam.fastq.gz", md5sum="123", size="456", task=my_task
    )
    qc = mock_accession_patched_qc.make_chip_replication_qc({}, gs_file=gsfile)
    assert (
        qc["reproducible_peaks"]
        == pipeline_qc["replication"]["reproducibility"][method][
            reproducible_peaks_source
        ]
    )
    if method == "idr":
        assert qc["idr_cutoff"] == idr_thresh
        for k in ["idr_parameters", "idr_dispersion_plot"]:
            assert all(i in qc[k] for i in ["href", "type", "download"])
    optimal_keys = ["rescue_ratio", "self_consistency_ratio", "reproducibility"]
    if current_set == pipeline_qc["replication"]["reproducibility"][method]["opt_set"]:
        for k in optimal_keys:
            assert qc[k] == pipeline_qc["replication"]["reproducibility"][method][k]


@pytest.mark.parametrize(
    "current_set", [("pooled-pr1_vs_pooled-pr2"), ("rep1_vs_rep2")]
)
def test_make_chip_peak_enrichment_qc(mocker, mock_accession_patched_qc, current_set):
    """
    There is not a significant difference between the way this qc is generated between
    histone and tf pipelines. As such, only tf is tested here.
    """
    mocker.patch.object(
        mock_accession_patched_qc.backend, "read_json", return_value=peak_enrichment_qc
    )
    task = {"inputs": {"prefix": current_set}, "outputs": []}
    my_task = Task("idr", task, analysis="qux")
    gsfile = GSFile(
        "foo", "gs://abc/spam.fastq.gz", md5sum="123", size="456", task=my_task
    )
    qc = mock_accession_patched_qc.make_chip_peak_enrichment_qc({}, gs_file=gsfile)
    if (
        current_set
        == peak_enrichment_qc["replication"]["reproducibility"]["idr"]["opt_set"]
    ):
        for k, v in peak_enrichment_qc["peak_stat"]["peak_region_size"][
            "idr_opt"
        ].items():
            assert qc[k] == v
    assert (
        qc["frip"]
        == peak_enrichment_qc["peak_enrich"]["frac_reads_in_peaks"]["idr"][current_set][
            "frip"
        ]
    )