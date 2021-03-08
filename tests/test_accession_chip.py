from contextlib import suppress as does_not_raise

import pytest

from accession.accession import AccessionChip
from accession.analysis import Analysis
from accession.encode_models import EncodeFile
from accession.file import GSFile
from accession.task import Task


@pytest.fixture
def gsfile_multiple_fastqs():
    task = {
        "inputs": {
            "prefix": "pooled-pr1_vs_pooled-pr2",
            "fastqs_R1": ["gs://abc/spam.fastq.gz", "gs://cde/eggs.fastq.gz"],
        },
        "outputs": {},
    }
    my_task = Task("my_task", task)
    return GSFile("foo", "gs://abc/spam.fastq.gz", task=my_task)


@pytest.fixture
def gsfile_multiple_fastqs_2():
    task = {
        "inputs": {
            "prefix": "pooled-pr1_vs_pooled-pr2",
            "fastqs_R1": ["gs://abc/spam.fastq.gz", "gs://cde/eggs.fastq.gz"],
        },
        "outputs": {},
    }
    my_task = Task("my_task", task)
    return GSFile("foo", "gs://cde/eggs.fastq.gz", task=my_task)


REP = "rep1"


@pytest.fixture
def mock_accession_patched_qc(mocker, mock_accession_chip, gsfile):
    """
    Performs shared patches to qc metric maker functions. Dependents on this fixture
    should patch mock_accession_chip.backend.read_json() to supply the appropriate qc stub
    """
    mocker.patch.object(
        mock_accession_chip.analysis, "get_files", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip, "get_atac_chip_pipeline_replicate", return_value=REP
    )
    mocker.patch.object(mock_accession_chip, "queue_qc", lambda output, *args: output)
    return mock_accession_chip


@pytest.fixture
def mock_accession_chip_unpatched_properties(
    mocker,
    mock_accession_gc_backend,
    mock_metadata,
    mock_accession_steps,
    server_name,
    common_metadata,
):
    """
    Mocked accession instance with dummy __init__ that doesn't do anything and pre-baked
    assembly property. @properties must be patched before instantiation
    """
    mocked_accession = AccessionChip(
        mock_accession_steps,
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        server_name,
        common_metadata,
        no_log_file=True,
    )
    return mocked_accession


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
    "general": {"pipeline_type": "tf", "peak_caller": "spp"},
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
    "general": {"pipeline_type": "histone", "peak_caller": "macs2"},
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
    "general": {"pipeline_type": "tf", "peak_caller": "spp"},
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


def test_assembly_no_files_matching_filekey_raises(
    mocker, mock_accession_chip_unpatched_properties
):
    mocker.patch.object(
        mock_accession_chip_unpatched_properties.analysis, "get_files", return_value=[]
    )
    with pytest.raises(ValueError):
        _ = mock_accession_chip_unpatched_properties.assembly


def test_assembly_portal_index_is_none_raises(
    mocker, mock_accession_chip_unpatched_properties, gsfile
):
    mocker.patch.object(
        mock_accession_chip_unpatched_properties.analysis,
        "get_files",
        return_value=[gsfile],
    )
    mocker.patch.object(
        mock_accession_chip_unpatched_properties,
        "get_encode_file_matching_md5_of_blob",
        return_value=None,
    )
    with pytest.raises(ValueError):
        _ = mock_accession_chip_unpatched_properties.assembly


def test_assembly_portal_index_assembly_is_none_raises(
    mocker, mock_accession_chip_unpatched_properties, gsfile
):
    mocker.patch.object(
        mock_accession_chip_unpatched_properties.analysis,
        "get_files",
        return_value=[gsfile],
    )
    mocker.patch.object(
        mock_accession_chip_unpatched_properties,
        "get_encode_file_matching_md5_of_blob",
        return_value=EncodeFile({"@id": "foo"}),
    )
    with pytest.raises(ValueError):
        _ = mock_accession_chip_unpatched_properties.assembly


def test_assembly(mocker, mock_accession_chip_unpatched_properties, gsfile):
    mocker.patch.object(
        mock_accession_chip_unpatched_properties.analysis,
        "get_files",
        return_value=[gsfile],
    )
    mocker.patch.object(
        mock_accession_chip_unpatched_properties,
        "get_encode_file_matching_md5_of_blob",
        return_value=EncodeFile({"@id": "foo", "assembly": "GRCh38"}),
    )
    result = mock_accession_chip_unpatched_properties.assembly
    assert result == "GRCh38"


def test_accession_chip_pipeline_version(
    mocker, mock_accession_chip_unpatched_properties, gsfile
):
    mocker.patch.object(
        mock_accession_chip_unpatched_properties.analysis,
        "get_files",
        return_value=[gsfile],
    )
    mocker.patch.object(
        gsfile, "read_json", return_value={"general": {"pipeline_ver": "v1.2.3"}}
    )
    result = mock_accession_chip_unpatched_properties.pipeline_version
    assert result == "1.2.3"


@pytest.mark.parametrize("peak_caller,expected", [("spp", "idr"), ("macs2", "overlap")])
def test_get_chip_pipeline_replication_method(peak_caller, expected):
    method = AccessionChip.get_chip_pipeline_replication_method(
        {"general": {"peak_caller": peak_caller}}
    )
    assert method == expected


@pytest.mark.parametrize(
    "qc,expected",
    [
        (
            {
                "general": {"peak_caller": "spp"},
                "replication": {
                    "reproducibility": {"idr": {"opt_set": "pooled-pr1_vs_pooled-pr2"}}
                },
            },
            {"preferred_default": True},
        ),
        (
            {
                "general": {"peak_caller": "macs2"},
                "replication": {
                    "reproducibility": {"overlap": {"opt_set": "rep1_vs_rep2"}}
                },
            },
            {},
        ),
    ],
)
def test_maybe_preferred_default_replicated(
    mocker, mock_accession_chip, gsfile, qc, expected
):
    mocker.patch.object(
        mock_accession_chip.analysis, "get_files", return_value=[gsfile]
    )
    mocker.patch.object(gsfile, "read_json", return_value=qc)
    mocker.patch.object(mock_accession_chip, "get_number_of_replicates", return_value=2)
    result = mock_accession_chip.maybe_preferred_default(gsfile)
    assert result == expected


@pytest.mark.parametrize(
    "task_name,peak_caller,expected",
    [
        ("idr_pr", "spp", {"preferred_default": True}),
        ("idr", "spp", {}),
        ("overlap_pr", "macs2", {"preferred_default": True}),
        ("overlap", "macs2", {}),
    ],
)
def test_maybe_preferred_default_unreplicated(
    mocker, mock_accession_chip, gsfile, task_name, peak_caller, expected
):
    mocker.patch.object(
        mock_accession_chip.analysis, "get_files", return_value=[gsfile]
    )
    mocker.patch.object(gsfile.task, "task_name", task_name)
    mocker.patch.object(
        gsfile, "read_json", return_value={"general": {"peak_caller": peak_caller}}
    )
    mocker.patch.object(mock_accession_chip, "get_number_of_replicates", return_value=1)
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
    mocker.patch.object(gsfile, "read_bytes", return_value=log_contents)
    with expectation:
        result = mock_accession_chip.add_mapped_read_length(gsfile)
        assert result == {"mapped_read_length": expected_value}


@pytest.mark.parametrize(
    "qc,condition,expected",
    [
        (
            {"general": {"seq_endedness": {"rep1": {"paired_end": True}}}},
            does_not_raise(),
            {"mapped_run_type": "paired-ended"},
        ),
        (
            {"general": {"seq_endedness": {"rep1": {"paired_end": False}}}},
            does_not_raise(),
            {"mapped_run_type": "single-ended"},
        ),
        (
            {"general": {"seq_endedness": {"rep1": {"paired_end": "true"}}}},
            pytest.raises(TypeError),
            {},
        ),
    ],
)
def test_accession_chip_add_mapped_run_type(
    mocker, mock_accession_chip, gsfile, qc, condition, expected
):
    mocker.patch.object(
        mock_accession_chip.analysis, "get_files", return_value=[gsfile]
    )
    mocker.patch.object(gsfile, "read_json", return_value=qc)
    mocker.patch.object(
        mock_accession_chip, "get_atac_chip_pipeline_replicate", return_value="rep1"
    )
    with condition:
        result = mock_accession_chip.add_mapped_run_type(gsfile)
        assert result == expected


@pytest.mark.parametrize(
    "task_name,num_replicates,expected",
    [
        ("macs2_signal_track", 1, {"preferred_default": True}),
        ("not_macs2", 1, {}),
        ("macs2_signal_track", 2, {}),
        ("macs2_signal_track_pooled", 3, {"preferred_default": True}),
    ],
)
def test_accession_chip_atac_maybe_preferred_default_bigwig(
    mocker, mock_accession_chip, gsfile, task_name, num_replicates, expected
):
    mocker.patch.object(
        gsfile, "get_task", return_value=mocker.Mock(task_name=task_name)
    )
    mocker.patch.object(
        mock_accession_chip, "get_number_of_replicates", return_value=num_replicates
    )
    result = mock_accession_chip.maybe_preferred_default_bigwig(gsfile)
    assert result == expected


@pytest.mark.parametrize(
    "gsfile_task,expected",
    [
        (Task("my_task", {"inputs": {"crop_length": 0}, "outputs": {}}), {}),
        (
            Task("my_task", {"inputs": {"crop_length": 10}, "outputs": {}}),
            {"cropped_read_length": 10},
        ),
    ],
)
def test_maybe_add_chip_cropped_read_length(
    mocker, mock_accession_chip, gsfile, gsfile_task, expected
):
    mocker.patch.object(
        mock_accession_chip.analysis, "get_tasks", return_value=[gsfile_task]
    )
    result = mock_accession_chip.maybe_add_cropped_read_length(gsfile)
    assert result == expected


@pytest.mark.parametrize(
    "gsfile_task,expected",
    [
        (
            Task(
                "my_task",
                {"inputs": {"crop_length": 0, "crop_length_tol": 2}, "outputs": {}},
            ),
            {},
        ),
        (
            Task(
                "my_task",
                {"inputs": {"crop_length": 10, "crop_length_tol": 2}, "outputs": {}},
            ),
            {"cropped_read_length_tolerance": 2},
        ),
    ],
)
def test_maybe_add_chip_cropped_read_length_tolerance(
    mocker, mock_accession_chip, gsfile, gsfile_task, expected
):
    mocker.patch.object(
        mock_accession_chip.analysis, "get_tasks", return_value=[gsfile_task]
    )
    result = mock_accession_chip.maybe_add_cropped_read_length_tolerance(gsfile)
    assert result == expected


@pytest.mark.parametrize(
    "processing_stage,align_qc",
    [("unfiltered", align_qc_dup), ("filtered", align_qc_nodup)],
)
def test_make_chip_alignment_qc(
    mocker, mock_accession_patched_qc, gsfile, processing_stage, align_qc
):
    mocker.patch.object(
        mock_accession_patched_qc.analysis, "get_files", return_value=[gsfile]
    )
    mocker.patch.object(gsfile, "read_json", return_value=align_qc)
    output_type = "alignments"
    qc_key = "nodup_samstat"
    if processing_stage == "unfiltered":
        output_type = " ".join([processing_stage, output_type])
        qc_key = "samstat"
    encode_file = EncodeFile(
        {"@id": "/files/foo/", "quality_metrics": [], "output_type": output_type}
    )
    qc = mock_accession_patched_qc.make_chip_alignment_qc(encode_file, file="foo")
    for k, v in qc.items():
        if k == "processing_stage":
            assert v == processing_stage
        else:
            assert v == align_qc["align"][qc_key][REP][k]


@pytest.fixture
def mock_accession_align_enrich(
    mocker, mock_accession_patched_qc, gsfile_multiple_fastqs, gsfile_multiple_fastqs_2
):
    mocker.patch.object(
        mock_accession_patched_qc.analysis,
        "search_up",
        return_value=[gsfile_multiple_fastqs, gsfile_multiple_fastqs_2],
    )
    mocker.patch.object(
        mock_accession_patched_qc.analysis,
        "search_down",
        return_value=[gsfile_multiple_fastqs],
    )
    mocker.patch.object(
        mock_accession_patched_qc.analysis,
        "get_files",
        return_value=[gsfile_multiple_fastqs],
    )
    mocker.patch.object(
        gsfile_multiple_fastqs, "read_json", return_value=align_enrich_qc
    )
    mocker.patch.object(gsfile_multiple_fastqs, "read_bytes", return_value=b"foo")
    return mock_accession_patched_qc


def test_make_chip_align_enrich_qc(
    mocker, mock_accession_align_enrich, gsfile_multiple_fastqs, encode_file_no_qc
):
    task = {
        "inputs": {"fastqs_R1": ["gs://cde/eggs.fastq.gz", "gs://abc/spam.fastq.gz"]},
        "outputs": {},
    }
    stub_task = Task("align_R1", task)
    mocker.patch.object(
        mock_accession_align_enrich.analysis, "get_tasks", return_value=[stub_task]
    )
    qc = mock_accession_align_enrich.make_chip_align_enrich_qc(
        encode_file_no_qc, file=gsfile_multiple_fastqs
    )
    keys = ["xcor_score", "jsd"]
    for key in keys:
        for k, v in align_enrich_qc["align_enrich"][key][REP].items():
            assert qc[k] == v
    for key in ["cross_correlation_plot", "jsd_plot", "gc_bias_plot"]:
        for prop in ["type", "download", "href"]:
            assert prop in qc[key]


def test_make_chip_align_enrich_qc_raises(
    mocker, mock_accession_align_enrich, gsfile_multiple_fastqs, encode_file_no_qc
):
    mocker.patch.object(
        mock_accession_align_enrich.analysis, "get_tasks", return_value=[]
    )
    with pytest.raises(ValueError):
        mock_accession_align_enrich.make_chip_align_enrich_qc(
            encode_file_no_qc, file=gsfile_multiple_fastqs
        )


def test_make_chip_library_qc(
    mocker, mock_accession_patched_qc, gsfile, encode_file_no_qc
):
    mocker.patch.object(
        mock_accession_patched_qc.analysis, "get_files", return_value=[gsfile]
    )
    mocker.patch.object(gsfile, "read_json", return_value=library_qc)
    qc = mock_accession_patched_qc.make_chip_library_qc(encode_file_no_qc, file="foo")
    for k, v in library_qc["align"]["dup"][REP].items():
        assert qc[k] == v
    for k, v in library_qc["lib_complexity"]["lib_complexity"][REP].items():
        assert qc[k] == v


def test_get_atac_chip_pipeline_replicate(mocker, mock_accession_chip, gsfile):
    mocker.patch.object(
        mock_accession_chip.analysis, "search_up", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip.analysis.metadata,
        "content",
        {"inputs": {"fastqs_rep1_R1": ["gs://abc/spam.fastq.gz"]}},
    )
    rep = mock_accession_chip.get_atac_chip_pipeline_replicate(gsfile)
    assert rep == "rep1"


def test_get_atac_chip_pipeline_replicate_control(mocker, mock_accession_chip, gsfile):
    mocker.patch.object(
        mock_accession_chip.analysis, "search_up", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip.analysis.metadata,
        "content",
        {"inputs": {"ctl_fastqs_rep1_R1": ["gs://abc/spam.fastq.gz"]}},
    )
    rep = mock_accession_chip.get_atac_chip_pipeline_replicate(gsfile)
    assert rep == "ctl1"


def test_get_atac_chip_pipeline_replicate_raises(mocker, mock_accession_chip, gsfile):
    mocker.patch.object(
        mock_accession_chip.analysis, "search_up", return_value=[gsfile]
    )
    mocker.patch.object(
        mock_accession_chip.analysis.metadata,
        "content",
        {"inputs": {"fastqs_rep1_R1": ["gs://abc/eggs.fastq.gz"]}},
    )
    with pytest.raises(ValueError):
        mock_accession_chip.get_atac_chip_pipeline_replicate(gsfile)


def test_get_atac_chip_pipeline_get_number_of_replicates(mocker, mock_accession_chip):
    mocker.patch.object(
        mock_accession_chip.analysis.metadata,
        "content",
        {
            "inputs": {
                "fastqs_rep1_R1": ["gs://abc/cde.fastq.gz"],
                "fastqs_rep1_R2": ["gs://abc/cde.fastq.gz"],
                "fastqs_rep2_R1": ["gs://spam/eggs.fastq.gz"],
                "ctl_fastqs_rep2_R1": ["gs://spam/eggs.fastq.gz"],
                "other": None,
            }
        },
    )
    result = mock_accession_chip.get_number_of_replicates()
    assert result == 2


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
    mocker,
    mock_accession_patched_qc,
    encode_file_no_qc,
    task_name,
    current_set,
    reproducible_peaks_source,
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
    mock_file = mocker.MagicMock()
    mock_file.read_json.return_value = pipeline_qc
    mocker.patch.object(
        mock_accession_patched_qc.analysis, "get_files", return_value=[mock_file]
    )
    mocker.patch.object(mock_accession_patched_qc, "get_attachment")
    if method == "idr":
        idr_thresh = 0.05
        task = {
            "inputs": {"prefix": current_set, "idr_thresh": idr_thresh},
            "outputs": {"idr_log": "gs://abc/idr.log", "idr_plot": "gs://abc/plot.png"},
        }
    else:
        task = {"inputs": {"prefix": current_set}, "outputs": []}
    my_task = Task(task_name, task)
    gsfile = GSFile("foo", "gs://abc/spam.fastq.gz", task=my_task)
    qc = mock_accession_patched_qc.make_chip_replication_qc(
        encode_file_no_qc, file=gsfile
    )
    assert (
        qc["reproducible_peaks"]
        == pipeline_qc["replication"]["reproducibility"][method][
            reproducible_peaks_source
        ]
    )
    if method == "idr":
        assert qc["idr_cutoff"] == idr_thresh
        for key in ["idr_parameters", "idr_dispersion_plot"]:
            assert key in qc
    optimal_keys = ["rescue_ratio", "self_consistency_ratio", "reproducibility"]
    if current_set == pipeline_qc["replication"]["reproducibility"][method]["opt_set"]:
        for k in optimal_keys:
            assert qc[k] == pipeline_qc["replication"]["reproducibility"][method][k]


@pytest.mark.parametrize(
    "current_set", [("pooled-pr1_vs_pooled-pr2"), ("rep1_vs_rep2")]
)
def test_make_chip_peak_enrichment_qc(
    mocker, mock_accession_patched_qc, encode_file_no_qc, current_set
):
    """
    There is not a significant difference between the way this qc is generated between
    histone and tf pipelines. As such, only tf is tested here.
    """
    mock_file = mocker.MagicMock()
    mock_file.read_json.return_value = peak_enrichment_qc
    mocker.patch.object(
        mock_accession_patched_qc.analysis, "get_files", return_value=[mock_file]
    )
    task = {"inputs": {"prefix": current_set}, "outputs": []}
    my_task = Task("idr", task)
    gsfile = GSFile("foo", "gs://abc/spam.fastq.gz", task=my_task)
    qc = mock_accession_patched_qc.make_chip_peak_enrichment_qc(
        encode_file_no_qc, file=gsfile
    )
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
