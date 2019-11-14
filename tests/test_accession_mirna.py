import pytest


@pytest.mark.docker
@pytest.mark.filesystem
def test_accession_mirna_replicated(accessioner_factory):
    factory = accessioner_factory(
        metadata_file="mirna_replicated_metadata.json", assay_name="mirna"
    )
    accessioner, expected_files = next(factory)
    accessioner.accession_steps()
    validate_accessioning(
        accessioner, expected_files, expected_num_files=12, dataset="ENCSR715NEZ"
    )


@pytest.mark.docker
@pytest.mark.filesystem
def test_accession_mirna_unreplicated(accessioner_factory):
    factory = accessioner_factory(
        metadata_file="mirna_unreplicated_metadata.json", assay_name="mirna"
    )
    accessioner, expected_files = next(factory)
    accessioner.accession_steps()
    validate_accessioning(
        accessioner, expected_files, expected_num_files=6, dataset="ENCSR543MWW"
    )


def validate_accessioning(accessioner, expected_files, expected_num_files, dataset):
    all_files = accessioner.conn.get(f"/files/", database=True)["@graph"]
    accessioner.conn.get(f"/files/?dataset=/experiments/{dataset}/", database=True)[
        "@graph"
    ]
    all_quality_metrics = [
        accessioner.conn.get(qm["@id"], database=True, frame="object")
        for qm in accessioner.conn.get("/quality-metrics/", database=True)["@graph"]
    ]
    excluded_types = ("reads", "genome index", "genome reference")
    files = [
        f
        for f in all_files
        if f["output_type"] not in excluded_types
        and f["dataset"] == f"/experiments/{dataset}/"
    ]
    assert len(files) == expected_num_files
    shared_keys_to_skip = ["submitted_by", "date_created", "@id", "uuid"]
    file_keys_to_skip = [
        "title",
        "accession",
        "file_size",
        "cloud_metadata",
        "href",
        "s3_uri",
        "no_file_available",
        "analysis_step_version",
        "content_md5sum",
        "matching_md5sum",
        "audit",
    ]
    qm_keys_to_skip = ["step_run"]
    for keys_to_skip in (file_keys_to_skip, qm_keys_to_skip):
        keys_to_skip.extend(shared_keys_to_skip)
    for partial_file in files:
        file = accessioner.conn.get(
            partial_file["@id"], frame="embedded", database=True
        )
        quality_metrics = [
            qm for qm in all_quality_metrics if file["@id"] in qm["quality_metric_of"]
        ]
        aliases = file["aliases"]
        expected = [f for f in expected_files if f["aliases"] == aliases][0]
        for key, expected_value in expected.items():
            if key in file_keys_to_skip:
                continue
            elif key == "step_run":
                for step_run_key in ("analysis_step_version", "aliases"):
                    assert file[key][step_run_key] == expected_value[step_run_key]
                assert file[key]["status"] == "in progress"
            elif key == "status":
                assert file[key] == "uploading"
            elif key in ("award", "lab"):
                assert file[key]["@id"] == expected_value["@id"]
            elif key == "file_size":
                assert file[key] == 3
            elif key == "derived_from":
                derived_from_aliases = []
                for i in all_files:
                    if i["@id"] in file[key]:
                        db_file = accessioner.conn.get(i["@id"], database=True)
                        derived_from_aliases.append(
                            (db_file["aliases"], db_file["md5sum"])
                        )
                expected_aliases = [
                    (f["aliases"], f["md5sum"])
                    for f in expected_files
                    if f["@id"] in expected_value
                ]
                assert sorted(derived_from_aliases) == sorted(expected_aliases)
            elif key == "quality_metrics":
                if not expected_value:
                    assert not quality_metrics
                else:
                    for expected_qm in expected_value:
                        posted_qms = [
                            qm
                            for qm in quality_metrics
                            if qm["@type"] == expected_qm["@type"]
                        ]
                        assert len(posted_qms) == 1
                        posted_qm = posted_qms[0]
                        for qm_key, qm_value in expected_qm.items():
                            if qm_key == "quality_metric_of":
                                assert len(qm_value) == len(posted_qm[qm_key])
                            elif qm_key in qm_keys_to_skip:
                                continue
                            elif qm_key == "status":
                                assert posted_qm[qm_key] == "in progress"
                            else:
                                assert qm_value == posted_qm[qm_key]
            else:
                assert file[key] == expected_value
