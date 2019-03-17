from accession.accession import COMMON_METADATA
import pdb


def test_common_metadata(accession, input_json):
    lab = input_json.get('accession.lab')
    award = input_json.get('accession.award')
    assert COMMON_METADATA['lab'] == lab
    assert COMMON_METADATA['award'] == award


def test_current_user(accession):
    current_user = accession.current_user
    assert 'users' in current_user
    assert len(current_user.split('/')) == 4


def test_file_at_portal(accession):
    fastq = accession.analysis.raw_fastqs[0]
    portal_file = accession.file_at_portal(fastq.filename)
    assert portal_file.get('fastq_signature')


def test_raw_files_accessioned(accession):
    assert accession.raw_files_accessioned()


def test_assembly(accession):
    assert accession.assembly == 'GRCh38'


def test_dataset(accession):
    assert accession.dataset.get('title')


def test_derived_from(accession, input_json):
    bowtie_step = accession.steps_and_params_json[0]
    analysis = accession.analysis
    task = analysis.get_tasks(bowtie_step['wdl_task_name'])[0]
    bam = [file for file in task.output_files if 'bam' in file.filekeys][0]
    raw_fastq_inputs = list(set(accession.raw_fastq_inputs(bam)))
    accession_ids = [accession.file_at_portal(file.filename).get('accession')
                     for file
                     in raw_fastq_inputs]
    params = bowtie_step['wdl_files'][0]['derived_from_files'][0]
    ancestors = accession.get_derived_from(bam,
                                           params.get('derived_from_task'),
                                           params.get('derived_from_filekey'),
                                           params.get('derived_from_output_type'),
                                           params.get('derived_from_inputs'))
    ancestor_accessions = [ancestor.split('/')[-2] for ancestor in ancestors]
    assert len(ancestor_accessions) == 2
    assert len(accession_ids) == len(ancestor_accessions)
    assert set(accession_ids) == set(ancestor_accessions)
