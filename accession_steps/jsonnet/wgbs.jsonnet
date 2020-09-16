{
  'wgbs_steps.json': {
    local contig_sizes_derived_from_file = {
      derived_from_filekey: 'contig_sizes',
      derived_from_task: 'extract',
      derived_from_inputs: true,
    },
    local bed_bigwig_derived_from_files = {
      derived_from_files: [
        {
          derived_from_filekey: 'bam',
          derived_from_task: 'map',
        },
        contig_sizes_derived_from_file,
      ],
    },
    'accession.steps': [
      {
        dcc_step_run: 'wgbs-alignment-step-run-v-1',
        dcc_step_version: '/analysis-step-versions/wgbs-alignment-step-v-1-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'fastqs',
                derived_from_inputs: true,
                derived_from_task: 'map',
              },
              {
                derived_from_filekey: 'index',
                derived_from_inputs: true,
                derived_from_task: 'map',
              },
              {
                derived_from_filekey: 'reference',
                derived_from_inputs: true,
                derived_from_task: 'map',
              },
            ],
            file_format: 'bam',
            filekey: 'bam',
            output_type: 'alignments',
            quality_metrics: [
              'gembs_alignment',
              'samtools_stats',
            ],
          },
        ],
        wdl_task_name: 'map',
      },
      {
        dcc_step_run: 'wgbs-extract-step-run-v-1',
        dcc_step_version: '/analysis-step-versions/wgbs-extract-step-v-1-0/',
        wdl_files: [
          bed_bigwig_derived_from_files + i
          for i in [
            {
              file_format: 'bed',
              file_format_type: 'bedMethyl',
              filekey: 'chg_bed',
              output_type: 'methylation state at CHG',
            },
            {
              file_format: 'bed',
              file_format_type: 'bedMethyl',
              filekey: 'chh_bed',
              output_type: 'methylation state at CHH',
            },
            {
              file_format: 'bed',
              file_format_type: 'bedMethyl',
              filekey: 'cpg_bed',
              output_type: 'methylation state at CPG',
              quality_metrics: [
                'cpg_correlation',
              ],
            },
            {
              file_format: 'bigWig',
              filekey: 'plus_strand_bw',
              output_type: 'plus strand methylation state at CpG',
            },
            {
              file_format: 'bigWig',
              filekey: 'minus_strand_bw',
              output_type: 'minus strand methylation state at CpG',
            },
          ]
        ],
        wdl_task_name: 'extract',
      },
      {
        dcc_step_run: 'wgbs-genotyping-extract-step-run-v-1',
        dcc_step_version: '/analysis-step-versions/wgbs-genotyping-extract-step-v-1-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'bam',
                derived_from_task: 'map',
              },
            ],
            file_format: 'bed',
            file_format_type: 'bedMethyl',
            filekey: 'smoothed_cpg_bed',
            output_type: 'smoothed methylation state at CPG',
          },
        ],
        wdl_task_name: 'bsmooth',
      },
      {
        dcc_step_run: 'wgbs-extract-format-conversion-step-run-v-1',
        dcc_step_version: '/analysis-step-versions/wgbs-extract-format-conversion-step-v-1-0/',
        wdl_files: [
          bed_bigwig_derived_from_files + i
          for i in [
            {
              derived_from_files: [
                contig_sizes_derived_from_file,
                {
                  derived_from_filekey: 'chg_bed',
                  derived_from_task: 'extract',
                },
              ],
              file_format: 'bigBed',
              file_format_type: 'bedMethyl',
              filekey: 'chg_bb',
              output_type: 'methylation state at CHG',
            },
            {
              derived_from_files: [
                contig_sizes_derived_from_file,
                {
                  derived_from_filekey: 'chh_bed',
                  derived_from_task: 'extract',
                },
              ],
              file_format: 'bigBed',
              file_format_type: 'bedMethyl',
              filekey: 'chh_bb',
              output_type: 'methylation state at CHH',
            },
            {
              derived_from_files: [
                contig_sizes_derived_from_file,
                {
                  derived_from_filekey: 'cpg_bed',
                  derived_from_task: 'extract',
                },
              ],
              file_format: 'bigBed',
              file_format_type: 'bedMethyl',
              filekey: 'cpg_bb',
              output_type: 'methylation state at CPG',
            },
          ]
        ],
        wdl_task_name: 'extract',
      },
      {
        dcc_step_run: 'wgbs-genotyping-extract-format-conversion-step-run-v-1',
        dcc_step_version: '/analysis-step-versions/wgbs-genotyping-extract-format-conversion-step-v-1-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'smoothed_cpg_bed',
                derived_from_task: 'bsmooth',
              },
              {
                derived_from_filekey: 'chrom_sizes',
                derived_from_inputs: true,
                derived_from_task: 'bsmooth',
              },
            ],
            file_format: 'bigBed',
            file_format_type: 'bedMethyl',
            filekey: 'smoothed_cpg_bigbed',
            output_type: 'smoothed methylation state at CPG',
          },
        ],
        wdl_task_name: 'bsmooth',
      },
      {
        dcc_step_run: 'wgbs-average-coverage-step-run-v-1',
        dcc_step_version: '/analysis-step-versions/wgbs-average-coverage-step-v-1-0/',
        wdl_files: [
          {
            derived_from_files: [
              {
                derived_from_filekey: 'cpg_bed',
                derived_from_task: 'extract',
              },
              {
                derived_from_filekey: 'chrom_sizes',
                derived_from_inputs: true,
                derived_from_task: 'make_coverage_bigwig',
              },
            ],
            file_format: 'bigWig',
            filekey: 'coverage_bigwig',
            output_type: 'CpG sites coverage',
          },
        ],
        wdl_task_name: 'make_coverage_bigwig',
      },
    ],
  },
}
