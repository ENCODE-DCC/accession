from accession.accession import COMMON_METADATA


def test_common_metadata(accession, input_json):
    lab = input_json.get("accession.lab")
    award = input_json.get("accession.award")
    assert COMMON_METADATA["lab"] == lab
    assert COMMON_METADATA["award"] == award


def test_current_user(accession):
    current_user = accession.current_user
    assert "users" in current_user
    assert len(current_user.split("/")) == 4


def test_file_at_portal(accession):
    fastq = accession.analysis.raw_fastqs[0]
    portal_file = accession.file_at_portal(fastq.filename)
    assert portal_file.get("fastq_signature")


def test_raw_files_accessioned(accession):
    assert accession.raw_files_accessioned()


def test_assembly(accession):
    assert accession.assembly == "mm10"


def test_dataset(accession):
    assert accession.dataset == "/experiments/ENCSR609OHJ/"


def test_get_derived_from(accession, input_json):
    bowtie_step = accession.steps_and_params_json[0]
    analysis = accession.analysis
    task = analysis.get_tasks(bowtie_step["wdl_task_name"])[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    raw_fastq_inputs = list(set(accession.raw_fastq_inputs(bam)))
    accession_ids = [
        accession.file_at_portal(file.filename).get("accession")
        for file in raw_fastq_inputs
    ]
    params = bowtie_step["wdl_files"][0]["derived_from_files"][0]
    ancestors = accession.get_derived_from(
        bam,
        params.get("derived_from_task"),
        params.get("derived_from_filekey"),
        params.get("derived_from_output_type"),
        params.get("derived_from_inputs"),
    )
    ancestor_accessions = [ancestor.split("/")[-2] for ancestor in ancestors]
    assert len(ancestor_accessions) == 2
    assert len(accession_ids) == len(ancestor_accessions)
    assert set(accession_ids) == set(ancestor_accessions)


def test_get_derived_from_all(accession, input_json):
    bowtie_step = accession.steps_and_params_json[0]
    analysis = accession.analysis
    task = analysis.get_tasks(bowtie_step["wdl_task_name"])[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    raw_fastq_inputs = list(set(accession.raw_fastq_inputs(bam)))
    accession_ids = [
        accession.file_at_portal(file.filename).get("accession")
        for file in raw_fastq_inputs
    ]
    derived_from_files = bowtie_step["wdl_files"][0]["derived_from_files"]
    ancestors = accession.get_derived_from_all(bam, derived_from_files)
    ancestor_accessions = [ancestor.split("/")[-2] for ancestor in ancestors]
    assert len(ancestor_accessions) == 2
    assert len(accession_ids) == len(ancestor_accessions)
    assert set(accession_ids) == set(ancestor_accessions)


def test_get_or_make_step_run(accession):
    bowtie_step = accession.steps_and_params_json[0]
    step_run = accession.get_or_make_step_run(
        accession.lab_pi,
        bowtie_step["dcc_step_run"],
        bowtie_step["dcc_step_version"],
        bowtie_step["wdl_task_name"],
    )
    assert "AnalysisStepRun" in step_run.get("@type")
    step_version = step_run.get("analysis_step_version")
    if isinstance(step_version, str):
        assert bowtie_step["dcc_step_version"] == step_version
    else:
        assert bowtie_step["dcc_step_version"] == step_version.get("@id")


def test_make_file_obj(accession):
    bowtie_step = accession.steps_and_params_json[0]
    analysis = accession.analysis
    task = analysis.get_tasks(bowtie_step["wdl_task_name"])[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    step_run = accession.get_or_make_step_run(
        accession.lab_pi,
        bowtie_step["dcc_step_run"],
        bowtie_step["dcc_step_version"],
        bowtie_step["wdl_task_name"],
    )
    file_params = bowtie_step["wdl_files"][0]
    obj = accession.make_file_obj(
        bam,
        file_params["file_format"],
        file_params["output_type"],
        step_run,
        file_params["derived_from_files"],
        file_format_type=file_params.get("file_format_type"),
    )
    assert obj.get("md5sum") and obj.get("file_size")
    assert len(obj.get("derived_from")) == 2


def test_accession_file(accession):
    bowtie_step = accession.steps_and_params_json[0]
    analysis = accession.analysis
    task = analysis.get_tasks(bowtie_step["wdl_task_name"])[0]
    bam = [file for file in task.output_files if "bam" in file.filekeys][0]
    step_run = accession.get_or_make_step_run(
        accession.lab_pi,
        bowtie_step["dcc_step_run"],
        bowtie_step["dcc_step_version"],
        bowtie_step["wdl_task_name"],
    )
    file_params = bowtie_step["wdl_files"][0]
    obj = accession.make_file_obj(
        bam,
        file_params["file_format"],
        file_params["output_type"],
        step_run,
        file_params["derived_from_files"],
        file_format_type=file_params.get("file_format_type"),
    )
    encode_file = accession.accession_file(obj, bam)
    assert encode_file.get("accession")
    assert encode_file.get("status") == "uploading"
    assert encode_file.get("submitted_file_name") == bam.filename


def test_accession_steps(accession):
    accession.accession_steps()
    for file in accession.new_files:
        if (
            file.get("output_type") == "optimal idr thresholded peaks"
            and file.get("file_format") == "bed"
            and file.get("file_format_type") == "narrowPeak"
        ):
            accessioned_file = file
    assert "TST" in accessioned_file.get("accession")
    accessioned_file = accession.conn.get(accessioned_file.get("accession"))
    assert len(accessioned_file.get("quality_metrics")) > 0
