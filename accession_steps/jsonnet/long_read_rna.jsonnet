/*
The reference genome can be the input to one of two tasks depending on the number of
spikeins. The same goes for the reference annotation GTF. For the spikeins, there are
three possible locations that they could appear.
*/
{
  'long_read_rna_no_spikeins_steps.json': LongReadRnaSteps(num_spikeins=0),
  'long_read_rna_one_spikein_steps.json': LongReadRnaSteps(num_spikeins=1),
  'long_read_rna_two_or_more_spikeins_steps.json': LongReadRnaSteps(num_spikeins=2),
  local LongReadRnaSteps(num_spikeins) = {
    local reference_genome = if num_spikeins == 0 then {
      derived_from_filekey: 'reference_fasta',
      derived_from_inputs: true,
      derived_from_task: 'clean_reference',
    } else {
      derived_from_filekey: 'files',
      derived_from_inputs: true,
      derived_from_task: 'combined_reference',
    },

    local reference_annotation = if num_spikeins == 0 then {
      derived_from_filekey: 'reference_fasta',
      derived_from_inputs: true,
      derived_from_task: 'clean_reference',
    } else {
      derived_from_filekey: 'files',
      derived_from_inputs: true,
      derived_from_task: 'combined_annotation',
    },

    local spikeins = if num_spikeins == 1 then [{
      derived_from_filekey: 'spikein_fasta',
      derived_from_inputs: true,
      derived_from_task: 'make_gtf_from_spikein_fasta',
    }] else if num_spikeins >= 2 then [{
      derived_from_filekey: 'files',
      derived_from_inputs: true,
      derived_from_task: 'combined_spikeins',
    }] else [{}],

    'accession.steps': [
      {
        dcc_step_run: '/analysis-steps/long-read-rna-seq-splice-junction-extraction-step-v-2/',
        dcc_step_version: '/analysis-step-versions/long-read-rna-seq-splice-junction-extraction-step-v-2-0/',
        wdl_files: [
          {
            derived_from_files: [
              reference_annotation,
              reference_genome,
            ],
            file_format: 'txt',
            filekey: 'splice_junctions',
            output_type: 'splice junctions',
          },
        ],
        wdl_task_name: 'get_splice_junctions',
      },
      {
        dcc_step_run: '/analysis-steps/long-read-rna-seq-alignments-step-v-2/',
        dcc_step_version: '/analysis-step-versions/long-read-rna-seq-alignments-step-v-2-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'fastq',
                derived_from_inputs: true,
                derived_from_task: 'minimap2',
              },
              reference_genome,
            ] + spikeins,
            file_format: 'bam',
            filekey: 'bam',
            output_type: 'unfiltered alignments',
            quality_metrics: [
              'long_read_rna_mapping',
            ],
          },
        ],
        wdl_task_name: 'minimap2',
      },
      {
        dcc_step_run: '/analysis-steps/long-read-rna-seq-filtering-step-v-2/',
        dcc_step_version: '/analysis-step-versions/long-read-rna-seq-filtering-step-v-2-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'bam',
                derived_from_task: 'minimap2',
              },
              reference_genome,
              {
                derived_from_filekey: 'splice_junctions',
                derived_from_task: 'get_splice_junctions',
              },
              {
                allow_empty: true,
                derived_from_filekey: 'variants',
                derived_from_inputs: true,
                derived_from_task: 'transcriptclean',
              },
            ] + spikeins,
            file_format: 'bam',
            filekey: 'labeled_bam',
            output_type: 'alignments',
            quality_metrics: [],
          },
        ],
        wdl_task_name: 'talon_label_reads',
      },
      {
        dcc_step_run: '/analysis-steps/long-read-rna-seq-quantification-step-v-2/',
        dcc_step_version: '/analysis-step-versions/long-read-rna-seq-quantification-step-v-2-0/',
        wdl_files: [
          {
            derived_from_files: [
              reference_annotation,
              {
                derived_from_filekey: 'labeled_bam',
                derived_from_task: 'talon_label_reads',
              },
            ],
            file_format: 'tsv',
            filekey: 'talon_abundance',
            output_type: 'transcript quantifications',
            quality_metrics: [
              'long_read_rna_quantification',
              'long_read_rna_correlation',
            ],
          },
        ],
        wdl_task_name: 'create_abundance_from_talon_db',
      },
      {
        dcc_step_run: '/analysis-steps/long-read-rna-seq-quantification-step-v-2/',
        dcc_step_version: '/analysis-step-versions/long-read-rna-seq-quantification-step-v-2-0/',
        wdl_files: [
          {
            derived_from_files: [
              reference_annotation,
              {
                derived_from_filekey: 'labeled_bam',
                derived_from_task: 'talon_label_reads',
              },
            ],
            file_format: 'gtf',
            filekey: 'gtf',
            output_type: 'transcriptome annotations',
            quality_metrics: [],
          },
        ],
        wdl_task_name: 'create_gtf_from_talon_db',
      },
    ],
  },
}
