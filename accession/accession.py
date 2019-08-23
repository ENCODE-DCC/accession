#!/usr/bin/python3
import json
import os
import requests
import logging
from base64 import b64encode
from encode_utils.connection import Connection
from requests.exceptions import HTTPError
from accession.analysis import Analysis
from accession.quality_metric import QualityMetric
from accession.helpers import string_to_number


COMMON_METADATA = {
    'lab': '',
    'award': ''
}

QC_MAP = {
    'cross_correlation':    'make_cross_correlation_qc',
    'samtools_flagstat':    'make_flagstat_qc',
    'idr':                  'make_idr_qc',
    'star':                 'make_star_qc_metric',
    'mirna_mapping':        'make_microrna_mapping_qc',
    'mirna_quantification': 'make_microrna_quantification_qc',
    'mirna_correlation':    'make_microrna_correlation_qc'
}


ASSEMBLIES = ['GRCh38', 'mm10']


class Accession(object):
    """docstring for Accession"""

    def __init__(self, steps, metadata_json, server, lab, award):
        super(Accession, self).__init__()
        self.set_lab_award(lab, award)
        self.analysis = Analysis(metadata_json)
        self.steps_and_params_json = self.file_to_json(steps).get('accession.steps')
        self.backend = self.analysis.backend
        self.conn = Connection(server)
        self.new_files = []
        self.new_qcs = []
        self.raw_qcs = []
        self.current_user = self.get_current_user()
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            filename='accession.log',
            format='%(asctime)s %(message)s',
            level=logging.DEBUG
        )

    def set_lab_award(self, lab, award):
        global COMMON_METADATA
        COMMON_METADATA['lab'] = lab
        COMMON_METADATA['award'] = award

    def get_current_user(self):
        path = '/session-properties' + '?format=json'
        response = requests.get(self.conn.dcc_url + path,
                                auth=self.conn.auth)
        if response.ok:
            user = response.json().get('user')
            if user:
                return user.get('@id')
            raise Exception('Authenticated user not found')
        else:
            raise Exception('Request to portal failed')

    def file_to_json(self, file):
        with open(file) as json_file:
            json_obj = json.load(json_file)
        return json_obj

    def get_step_run_id(self, encode_file):
        step_run = encode_file.get('step_run')
        if isinstance(step_run, str):
            step_run_id = step_run
        elif isinstance(step_run, dict):
            step_run_id = step_run.get('@id')
        return step_run_id

    def accession_fastqs(self):
        pass

    def wait_for_portal(self):
        pass

    def file_at_portal(self, file):
        self.wait_for_portal()
        md5sum = self.backend.md5sum(file)
        search_param = [('md5sum', md5sum), ('type', 'File')]
        encode_file = self.conn.search(search_param)
        if len(encode_file) > 0:
            return self.conn.get(encode_file[0].get('accession'))

    def raw_fastq_inputs(self, file):
        if not file.task and 'fastqs' in file.filekeys:
            yield file
        if file.task:
            for input_file in file.task.input_files:
                yield from self.raw_fastq_inputs(input_file)

    def raw_files_accessioned(self):
        for file in self.analysis.raw_fastqs:
            if not self.file_at_portal(file.filename):
                return False
        return True

    def accession_file(self, encode_file, gs_file):
        file_exists = self.file_at_portal(gs_file.filename)
        submitted_file_path = {'submitted_file_name': gs_file.filename}
        if file_exists:
            self.logger.warning(
                'Attempting to post duplicate file of %s with md5sum %s',
                file_exists,
                encode_file.get('md5sum')
            )
        local_file = self.backend.download(gs_file.filename)[0]
        encode_file['submitted_file_name'] = local_file
        encode_posted_file = self.conn.post(encode_file)
        os.remove(local_file)
        encode_posted_file = self.patch_file(
            encode_posted_file,
            submitted_file_path
        )
        self.new_files.append(encode_posted_file)
        return encode_posted_file
        return file_exists

    def patch_file(self, encode_file, new_properties):
        new_properties[self.conn.ENCID_KEY] = encode_file.get('accession')
        return self.conn.patch(new_properties, extend_array_values=False)

    def get_or_make_step_run(self, lab_prefix, run_name, step_version, task_name):
        docker_tag = self.analysis.get_tasks(task_name)[0].docker_image.split(':')[1]
        payload = {'aliases': ["{}:{}-{}".format(lab_prefix, run_name, docker_tag)],
                   'status': 'released',
                   'analysis_step_version': step_version}
        payload[Connection.PROFILE_KEY] = 'analysis_step_runs'
        return self.conn.post(payload)

    @property
    def assembly(self):
        pipeline_name = self.analysis.metadata.get('workflowName')
        if pipeline_name == 'mirna_seq_pipeline':
            files = self.analysis.get_files(filekey='annotation')
            if files:
                annotation = self.file_at_portal(files[0].filename)
            return annotation.get('assembly', '')
        elif pipeline_name == 'atac':
            assembly = [reference
                        for reference
                        in ASSEMBLIES
                        if reference
                        in self.analysis.get_tasks('read_genome_tsv')[0].outputs.get(
                            'genome', {}).get('ref_fa', '')]
            return assembly[0] if len(assembly) > 0 else ''

    @property
    def genome_annotation(self):
        pipeline_name = self.analysis.metadata.get('workflowName')
        if pipeline_name == 'mirna_seq_pipeline':
            files = self.analysis.get_files(filekey='annotation')
            if files:
                annotation = self.file_at_portal(files[0].filename)
            return annotation.get('genome_annotation', '')

    @property
    def lab_pi(self):
        return COMMON_METADATA['lab'].split('/labs/')[1].split('/')[0]

    @property
    def dataset(self):
        return self.file_at_portal(
            self.analysis.raw_fastqs[0].filename).get('dataset')

    @property
    def assay_term_name(self):
        return self.conn.get(self.dataset).get('assay_term_name')

    @property
    def is_replicated(self):
        bio_reps = set([
            rep.get('biological_replicate_number')
            for rep
            in self.conn.get(self.dataset).get('replicates')
        ])
        return True if len(bio_reps) > 1 else False

    def file_from_template(self,
                           file,
                           file_format,
                           output_type,
                           step_run,
                           derived_from,
                           dataset,
                           file_format_type=None):
        file_name = file.filename.split('gs://')[-1].replace('/', '-')
        obj = {
            'status':               'uploading',
            'aliases':              ['{}:{}'.format(self.lab_pi, file_name)],
            'file_format':          file_format,
            'output_type':          output_type,
            'assembly':             self.assembly,
            'dataset':              dataset,
            'step_run':             step_run.get('@id'),
            'derived_from':         derived_from,
            'file_size':            file.size,
            'md5sum':               file.md5sum
        }
        if file_format_type:
            obj['file_format_type'] = file_format_type
        if self.genome_annotation:
            obj['genome_annotation'] = self.genome_annotation
        obj[Connection.PROFILE_KEY] = 'file'
        obj.update(COMMON_METADATA)
        return obj

    def get_derived_from_all(self, file, files):
        ancestors = []
        for ancestor in files:
            ancestors.append(
                self.get_derived_from(file,
                                      ancestor.get('derived_from_task'),
                                      ancestor.get('derived_from_filekey'),
                                      ancestor.get('derived_from_output_type'),
                                      ancestor.get('derived_from_inputs')))
        return list(self.flatten(ancestors))

    def flatten(self, nested_list):
        if isinstance(nested_list, str):
            yield nested_list
        if isinstance(nested_list, list):
            for item in nested_list:
                yield from self.flatten(item)

    # Returns list of accession ids of files on portal or recently accessioned
    def get_derived_from(self, file, task_name, filekey,
                         output_type=None, inputs=False):
        derived_from_files = self.analysis.search_up(file.task,
                                                     task_name,
                                                     filekey,
                                                     inputs)
        encode_files = [self.file_at_portal(gs_file.filename)
                        for gs_file
                        in derived_from_files]
        accessioned_files = encode_files + self.new_files
        accessioned_files = [x for x in accessioned_files if x is not None]
        derived_from_accession_ids = []
        for gs_file in derived_from_files:
            for encode_file in accessioned_files:
                if gs_file.md5sum == encode_file.get('md5sum'):
                    # Optimal peaks can be mistaken for conservative peaks
                    # when their md5sum is the same
                    if output_type and output_type != encode_file.get('output_type'):
                        continue
                    derived_from_accession_ids.append(encode_file.get('accession'))
        derived_from_accession_ids = list(set(derived_from_accession_ids))

        # Raise exception when some or all of the derived_from files
        # are missing from the portal

        missing = '\n'.join(['{}: {}'.format(filekey, filename)
                             for filename
                             in map(lambda x: x.filename, derived_from_files)])
        if not derived_from_accession_ids:
            raise Exception('Missing all of the derived_from files on the portal')
        if len(derived_from_accession_ids) != len(derived_from_files):
            raise Exception('Missing some of the derived_from files on the portal')
        return ['/files/{}/'.format(accession_id)
                for accession_id in derived_from_accession_ids]

    # File object to be accessioned
    def make_file_obj(self, file, file_format, output_type, step_run,
                      derived_from_files, file_format_type=None):
        derived_from = self.get_derived_from_all(file,
                                                 derived_from_files)
        return self.file_from_template(file,
                                       file_format,
                                       output_type,
                                       step_run,
                                       derived_from,
                                       self.dataset,
                                       file_format_type)

    def get_bio_replicate(self, encode_file, string=True):
        replicate = encode_file.get('biological_replicates')[0]
        if string:
            return str(replicate)
        return int(replicate)

    def post_qcs(self):
        for qc in self.raw_qcs:
            qc.payload.update({"quality_metric_of": qc.files})
            self.new_qcs.append(self.conn.post(qc.payload,
                                               require_aliases=False))

    def make_idr_qc(self, encode_file, gs_file):
        if self.file_has_qc(encode_file, 'IDRQualityMetric'):
            return
        qc = self.backend.read_json(self.analysis.get_files('qc_json')[0])
        idr_qc = qc['idr_frip_qc']
        replicate = self.get_bio_replicate(encode_file)
        rep_pr = idr_qc['rep' + replicate + '-pr']
        frip_score = rep_pr['FRiP']
        idr_peaks = qc['ataqc']['rep' + replicate]['IDR peaks'][0]
        qc_object = {}
        qc_object['F1'] = frip_score
        qc_object['N1'] = idr_peaks
        idr_cutoff = self.analysis.metadata['inputs']['atac.idr_thresh']
        # Strongly expects that plot exists
        plot_png = self.analysis.search_up(gs_file.task,
                                           'idr_pr',
                                           'idr_plot')[0]
        qc_object.update({
            'IDR_cutoff':                           idr_cutoff,
            'IDR_plot_rep{}_pr'.format(replicate):  self.get_attachment(plot_png, 'image/png')})
        return self.queue_qc(qc_object,
                             encode_file,
                             'idr-quality-metrics')

    def make_flagstat_qc(self, encode_bam_file, gs_file):
        # Return early if qc metric exists
        if self.file_has_qc(encode_bam_file, 'SamtoolsFlagstatsQualityMetric'):
            return
        qc = self.backend.read_json(self.analysis.get_files('qc_json')[0])
        replicate = self.get_bio_replicate(encode_bam_file)
        flagstat_qc = qc['nodup_flagstat_qc']['rep' + replicate]
        for key, value in flagstat_qc.items():
            if '_pct' in key:
                flagstat_qc[key] = '{}%'.format(value)
        return self.queue_qc(flagstat_qc,
                             encode_bam_file,
                             'samtools-flagstats-quality-metric')

    def make_cross_correlation_qc(self, encode_bam_file, gs_file):
        # Return early if qc metric exists
        if self.file_has_qc(encode_bam_file, 'ComplexityXcorrQualityMetric'):
            return
        qc = self.backend.read_json(self.analysis.get_files('qc_json')[0])
        plot_pdf = self.analysis.search_down(gs_file.task,
                                             'xcor',
                                             'plot_pdf')[0]
        read_length_file = self.analysis.search_up(gs_file.task,
                                                   'bowtie2',
                                                   'read_len_log')[0]
        read_length = int(self.backend.read_file(read_length_file.filename).decode())
        replicate = self.get_bio_replicate(encode_bam_file)
        xcor_qc = qc['xcor_score']['rep' + replicate]
        pbc_qc = qc['pbc_qc']['rep' + replicate]
        xcor_object = {
            'NRF':                  pbc_qc['NRF'],
            'PBC1':                 pbc_qc['PBC1'],
            'PBC2':                 pbc_qc['PBC2'],
            'NSC':                  xcor_qc['NSC'],
            'RSC':                  xcor_qc['RSC'],
            'sample size':          xcor_qc['num_reads'],
            "fragment length":      xcor_qc['est_frag_len'],
            "paired-end":           self.analysis.metadata['inputs']['atac.paired_end'],
            "read length":          read_length,
            "cross_correlation_plot": self.get_attachment(plot_pdf, 'application/pdf')
        }
        return self.queue_qc(xcor_object,
                             encode_bam_file,
                             'complexity-xcorr-quality-metrics')

    def make_star_qc_metric(self, encode_bam_file, gs_file):
        if self.file_has_qc(encode_bam_file, 'StarQualityMetric'):
            return
        qc_file = self.analysis.get_files(filename=gs_file.task.outputs['star_qc_json'])[0]
        qc = self.backend.read_json(qc_file)
        star_qc_metric = qc.get('star_qc_metric')
        del star_qc_metric['Started job on']
        del star_qc_metric['Started mapping on']
        del star_qc_metric['Finished on']
        for key, value in star_qc_metric.items():
            star_qc_metric[key] = string_to_number(value)
        return self.queue_qc(star_qc_metric,
                             encode_bam_file,
                             'star-quality-metric')

    def make_microrna_quantification_qc(self, encode_file, gs_file):
        if self.file_has_qc(encode_file, 'MicroRnaQuantificationQualityMetric'):
            return
        qc_file = self.analysis.get_files(filename=gs_file.task.outputs['star_qc_json'])[0]
        qc = self.backend.read_json(qc_file)
        expressed_mirnas_qc = qc['expressed_mirnas']
        return self.queue_qc(expressed_mirnas_qc,
                             encode_file,
                             'micro-rna-quantification-quality-metric')

    def make_microrna_mapping_qc(self, encode_file, gs_file):
        if self.file_has_qc(encode_file, 'MicroRnaMappingQualityMetric'):
            return
        qc_file = self.analysis.get_files(filename=gs_file.task.outputs['star_qc_json'])[0]
        qc = self.backend.read_json(qc_file)
        aligned_reads_qc = qc['aligned_reads']
        return self.queue_qc(aligned_reads_qc,
                             encode_file,
                             'micro-rna-mapping-quality-metric')

    def make_microrna_correlation_qc(self, encode_file, gs_file):
        """
        Returns without queueing this QC for posting if the experiment is not replicated, since
        correlation is computed between pairs of replicates.
        """
        if self.file_has_qc(encode_file, 'CorrelationQualityMetric') or not self.is_replicated:
            return
        qc_file = self.analysis.search_down(gs_file.task,
                                            'spearman_correlation',
                                            'spearman_json')[0]
        qc = self.backend.read_json(qc_file)
        spearman_value = qc['spearman_correlation']['spearman_correlation']
        spearman_correlation_qc = {'Spearman correlation': spearman_value}
        return self.queue_qc(spearman_correlation_qc,
                             encode_file,
                             'correlation-quality-metric',
                             shared=True)

    def queue_qc(self, qc, encode_file, profile, shared=False):
        step_run_id = self.get_step_run_id(encode_file)
        qc.update({
            'step_run':             step_run_id,
            'status':               "released",
        })
        if self.assay_term_name:
            qc['assay_term_name'] = self.assay_term_name
        qc.update(COMMON_METADATA)
        qc[Connection.PROFILE_KEY] = profile
        # Shared QCs will have two or more file ids
        # under the 'quality_metric_of' property
        # and payload must be the same for all
        if shared:
            for item in self.raw_qcs:
                if item.payload == qc:
                    item.files.append(encode_file.get('@id'))
                    return
        self.raw_qcs.append(QualityMetric(qc, encode_file.get('@id')))

    def file_has_qc(self, encode_file, qc_name):
        if list(filter(lambda x: qc_name in x['@type'],
                       encode_file['quality_metrics'])):
            return True
        return False

    def get_attachment(self, gs_file, mime_type):
        contents = self.backend.read_file(gs_file.filename)
        contents = b64encode(contents)
        if type(contents) is bytes:
            # The Portal treats the contents as string "b'bytes'"
            contents = str(contents).replace('b', '', 1).replace('\'', '')
        obj = {
            'type': mime_type,
            'download': gs_file.filename.split('/')[-1],
            'href': 'data:{};base64,{}'.format(mime_type,
                                               contents)
        }
        return obj

    def accession_step(self, single_step_params):
        step_run = self.get_or_make_step_run(
            self.lab_pi,
            single_step_params['dcc_step_run'],
            single_step_params['dcc_step_version'],
            single_step_params['wdl_task_name'])
        accessioned_files = []
        for task in self.analysis.get_tasks(single_step_params['wdl_task_name']):
            for file_params in single_step_params['wdl_files']:
                for wdl_file in [file
                                 for file
                                 in task.output_files
                                 if file_params['filekey']
                                 in file.filekeys]:

                    # Conservative IDR thresholded peaks may have
                    # the same md5sum as optimal one
                    try:
                        obj = self.make_file_obj(wdl_file,
                                                 file_params['file_format'],
                                                 file_params['output_type'],
                                                 step_run,
                                                 file_params['derived_from_files'],
                                                 file_format_type=file_params.get('file_format_type'))
                        encode_file = self.accession_file(obj, wdl_file)
                    except Exception as e:
                        if 'Conflict' in str(e) and file_params.get('possible_duplicate'):
                            continue
                        elif 'Missing' in str(e):
                            raise
                        else:
                            raise

                    # Parameter file inputted assumes Accession implements
                    # the methods to attach the quality metrics
                    quality_metrics = file_params.get('quality_metrics', [])
                    for qc in quality_metrics:
                        qc_method = getattr(self, QC_MAP[qc])
                        # Pass encode file with
                        # calculated properties
                        qc_method(self.conn.get(encode_file.get('accession'), database=True),
                                  wdl_file)
                    accessioned_files.append(encode_file)
        return accessioned_files

    def accession_steps(self):
        for step in self.steps_and_params_json:
            self.accession_step(step)
        self.post_qcs()
