/*depending on Boolean run_kallisto, include the kallisto output file in the template or omit it.
*/
{
  'bulk_rna_no_kallisto_steps.json': std.prune(BulkRnaSteps(run_kallisto=false)),
  'bulk_rna_steps.json': BulkRnaSteps(run_kallisto=true),
  local BulkRnaSteps(run_kallisto) = {
    local kallisto_item = if run_kallisto then
      {
        dcc_step_run: '/analysis-steps/bulk-rna-seq-kallisto-quantification-step-v-1/',
        dcc_step_version: '/analysis-step-versions/bulk-rna-seq-kallisto-quantification-step-v-1-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'fastqs_R1',
                derived_from_inputs: true,
                derived_from_task: 'kallisto',
              },
              {
                derived_from_filekey: 'fastqs_R2',
                derived_from_inputs: true,
                derived_from_task: 'kallisto',
              },
              {
                derived_from_filekey: 'kallisto_index',
                derived_from_inputs: true,
                derived_from_task: 'kallisto',
              },
            ],
            file_format: 'tsv',
            filekey: 'quants',
            output_type: 'transcript quantifications',
          },
        ],
        wdl_task_name: 'kallisto',
      },

    'accession.steps': [
      kallisto_item,
      {
        dcc_step_run: '/analysis-steps/bulk-rna-seq-alignment-step-v-1/',
        dcc_step_version: '/analysis-step-versions/bulk-rna-seq-alignment-step-v-1-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'fastqs_R1',
                derived_from_inputs: true,
                derived_from_task: 'align',
              },
              {
                derived_from_filekey: 'fastqs_R2',
                derived_from_inputs: true,
                derived_from_task: 'align',
              },
              {
                derived_from_filekey: 'index',
                derived_from_inputs: true,
                derived_from_task: 'align',
              },
            ],
            file_format: 'bam',
            filekey: 'genomebam',
            output_type: 'alignments',
            quality_metrics: [
              'star_mapping_qc',
              'genome_flagstat_qc',
            ],
          },
          {
            derived_from_files: [
              {
                derived_from_filekey: 'fastqs_R1',
                derived_from_inputs: true,
                derived_from_task: 'align',
              },
              {
                derived_from_filekey: 'fastqs_R2',
                derived_from_inputs: true,
                derived_from_task: 'align',
              },
              {
                derived_from_filekey: 'index',
                derived_from_inputs: true,
                derived_from_task: 'align',
              },
            ],
            file_format: 'bam',
            filekey: 'annobam',
            output_type: 'transcriptome alignments',
            quality_metrics: [
              'star_mapping_qc',
              'anno_flagstat_qc',
              'reads_by_gene_type_qc',
            ],
          },
        ],
        wdl_task_name: 'align',
      },
      {
        dcc_step_run: '/analysis-steps/bulk-rna-seq-star-signal-generation-step-v-1/',
        dcc_step_version: '/analysis-step-versions/bulk-rna-seq-star-signal-generation-step-v-1-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'chrom_sizes',
                derived_from_inputs: true,
                derived_from_task: 'bam_to_signals',
              },
              {
                derived_from_filekey: 'genomebam',
                derived_from_task: 'align',
              },
            ],
            file_format: 'bigWig',
            filekey: 'unique_unstranded',
            output_type: 'signal of unique reads',
            maybe_preferred_default: true,
          },
          {
            derived_from_files: [
              {
                derived_from_filekey: 'chrom_sizes',
                derived_from_inputs: true,
                derived_from_task: 'bam_to_signals',
              },
              {
                derived_from_filekey: 'genomebam',
                derived_from_task: 'align',
              },
            ],
            file_format: 'bigWig',
            filekey: 'all_unstranded',
            output_type: 'signal of all reads',
            maybe_preferred_default: true,
          },
          {
            derived_from_files: [
              {
                derived_from_filekey: 'chrom_sizes',
                derived_from_inputs: true,
                derived_from_task: 'bam_to_signals',
              },
              {
                derived_from_filekey: 'genomebam',
                derived_from_task: 'align',
              },
            ],
            file_format: 'bigWig',
            filekey: 'unique_plus',
            output_type: 'plus strand signal of unique reads',
            maybe_preferred_default: true,
          },
          {
            derived_from_files: [
              {
                derived_from_filekey: 'chrom_sizes',
                derived_from_inputs: true,
                derived_from_task: 'bam_to_signals',
              },
              {
                derived_from_filekey: 'genomebam',
                derived_from_task: 'align',
              },
            ],
            file_format: 'bigWig',
            filekey: 'unique_minus',
            output_type: 'minus strand signal of unique reads',
            maybe_preferred_default: true,
          },
          {
            derived_from_files: [
              {
                derived_from_filekey: 'chrom_sizes',
                derived_from_inputs: true,
                derived_from_task: 'bam_to_signals',
              },
              {
                derived_from_filekey: 'genomebam',
                derived_from_task: 'align',
              },
            ],
            file_format: 'bigWig',
            filekey: 'all_plus',
            output_type: 'plus strand signal of all reads',
            maybe_preferred_default: true,
          },
          {
            derived_from_files: [
              {
                derived_from_filekey: 'chrom_sizes',
                derived_from_inputs: true,
                derived_from_task: 'bam_to_signals',
              },
              {
                derived_from_filekey: 'genomebam',
                derived_from_task: 'align',
              },
            ],
            file_format: 'bigWig',
            filekey: 'all_minus',
            output_type: 'minus strand signal of all reads',
            maybe_preferred_default: true,
          },
        ],
        wdl_task_name: 'bam_to_signals',
      },
      {
        dcc_step_run: '/analysis-steps/bulk-rna-seq-rsem-quantification-step-v-1/',
        dcc_step_version: '/analysis-step-versions/bulk-rna-seq-rsem-quantification-step-v-1-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'rsem_index',
                derived_from_inputs: true,
                derived_from_task: 'rsem_quant',
              },
              {
                derived_from_filekey: 'annobam',
                derived_from_task: 'align',
              },
            ],
            file_format: 'tsv',
            filekey: 'genes_results',
            output_type: 'gene quantifications',
            quality_metrics: [
              'number_of_genes_detected_qc',
              'mad_qc_metric',
            ],
          },
          {
            derived_from_files: [
              {
                derived_from_filekey: 'rsem_index',
                derived_from_inputs: true,
                derived_from_task: 'rsem_quant',
              },
              {
                derived_from_filekey: 'annobam',
                derived_from_task: 'align',
              },
            ],
            file_format: 'tsv',
            filekey: 'isoforms_results',
            output_type: 'transcript quantifications',
          },
        ],
        wdl_task_name: 'rsem_quant',
      },
    ],
    raw_fastqs_keys: [
      'fastqs_R1',
      'fastqs_R2',
    ],
  },
}
