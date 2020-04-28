/*
File layout:
    - shared template parts
    - experiment ChIP map-only template
    - control ChIP map-only template (nearly identical except for slighly different QC)
    - TF ChIP peak calling template
    - histone ChIP peak calling template
    - MINT ChIP peak calling template
    - consolidated TF mapping and peak calling template
    - consolidated histone mapping and peak calling template
    - consolidated MINT ChIP mapping and peak calling template

After running `jsonnet`, this will produce 8 JSON files. 2 map only accessioning
templates, 3 pipeline-specific peak calling accessioning templates, and 3
pipeline-specific mapping and peak calling accessioning templates.
*/
{
  local bed_bigwig_derived_from_files = [
    {
      derived_from_filekey: 'nodup_bam',
      derived_from_task: 'filter',
      disallow_tasks: [
        'choose_ctl',
      ],
    },
    {
      derived_from_filekey: 'bam',
      derived_from_inputs: true,
      derived_from_task: 'bam2ta_ctl',
    },
  ],
  /* We insert the blacklist into the middle of the list so the array order is the same
  as the existing templates */
  local BedBigwigBlacklistDerivedFromFiles(
    blacklist_derived_from_task,
    derived_from_filekey='blacklist',
  ) = [bed_bigwig_derived_from_files[0]] + [{
    derived_from_filekey: derived_from_filekey,
    derived_from_inputs: true,
    derived_from_task: blacklist_derived_from_task,
  }] + [bed_bigwig_derived_from_files[1]],
  local bigwig_wdl_files = [
    {
      derived_from_files: bed_bigwig_derived_from_files,
      file_format: 'bigWig',
      filekey: 'pval_bw',
      output_type: 'signal p-value',
      quality_metrics: [],
    },
    {
      derived_from_files: bed_bigwig_derived_from_files,
      file_format: 'bigWig',
      filekey: 'fc_bw',
      output_type: 'fold change over control',
      quality_metrics: [],
    },
  ],
  local ChipMapOnlySteps(is_control=false) = {
    local step_run = 'chip-seq-alignment-step-v-2',
    local step_version = '/analysis-step-versions/chip-seq-alignment-step-v-2-0/',
    'accession.steps': [
      {
        dcc_step_run: step_run,
        dcc_step_version: step_version,
        wdl_files: [
          {
            callbacks: [
              'add_mapped_read_length',
              'maybe_add_cropped_read_length',
            ],
            derived_from_files: [
              {
                derived_from_filekey: 'idx_tar',
                derived_from_inputs: true,
                derived_from_task: 'align',
              },
              self.derived_from_files[0] { derived_from_filekey: 'fastqs_R1' },
              self.derived_from_files[0] { allow_empty: true, derived_from_filekey: 'fastqs_R2' },
            ],
            file_format: 'bam',
            filekey: 'bam',
            output_type: 'unfiltered alignments',
            quality_metrics: [
              'chip_alignment',
            ],
          },
        ],
        wdl_task_name: 'align',
      },
      {
        dcc_step_run: step_run,
        dcc_step_version: step_version,
        wdl_files: [
          {
            callbacks: [
              'add_mapped_read_length',
              'maybe_add_cropped_read_length',
            ],
            derived_from_files: $['chip_map_only_steps.json']['accession.steps'][0].wdl_files[0].derived_from_files,
            file_format: 'bam',
            filekey: 'nodup_bam',
            output_type: 'alignments',
            quality_metrics: [
              'chip_alignment',
            ] + (if !is_control then ['chip_align_enrich'] else []) + [
              'chip_library',
            ],
          },
        ],
        wdl_task_name: 'filter',
      },
    ],
    raw_fastqs_keys: [
      'fastqs_R1',
      'fastqs_R2',
    ],
  },
  'chip_map_only_steps.json': ChipMapOnlySteps(),
  'control_chip_steps.json': ChipMapOnlySteps(is_control=true),
  'tf_chip_peak_call_only_steps.json': {
    local file_format_type = 'narrowPeak',
    local shared_file_props = {
      file_format_type: file_format_type,
      output_type: 'IDR thresholded peaks',
      quality_metrics: [
        'chip_replication',
        'chip_peak_enrichment',
      ],
    },
    local IdrWdlFiles(blacklist_derived_from_task, callbacks=[],) = [
      {
        derived_from_files: bed_bigwig_derived_from_files,
        file_format: 'bed',
        file_format_type: file_format_type,
        filekey: 'idr_unthresholded_peak',
        output_type: 'IDR ranked peaks',
        quality_metrics: [],
      },
      (
        if std.length(callbacks) != 0 then { callbacks: callbacks } else {}
      ) + {
        derived_from_files: BedBigwigBlacklistDerivedFromFiles(blacklist_derived_from_task),
        file_format: 'bed',
        filekey: 'bfilt_idr_peak',
      } + shared_file_props,
    ],
    local FormatConversionWdlFiles(derived_from_task, callbacks=[],) = [
      (
        if std.length(callbacks) != 0 then { callbacks: callbacks } else {}
      ) + {
        derived_from_files: [
          {
            derived_from_filekey: 'bfilt_idr_peak',
            derived_from_task: derived_from_task,
          },
        ],
        file_format: 'bigBed',
        filekey: 'bfilt_idr_peak_bb',
      } + shared_file_props,
    ],
    'accession.steps': [
      {
        dcc_step_run: 'tf-chip-signal-generation-step-v-1',
        dcc_step_version: '/analysis-step-versions/tf-chip-signal-generation-step-v-1-0/',
        wdl_files: bigwig_wdl_files,
        wdl_task_name: 'macs2_signal_track',
      },
      {
        dcc_step_run: 'tf-chip-pooled-signal-generation-step-v-1',
        dcc_step_version: '/analysis-step-versions/tf-chip-pooled-signal-generation-step-v-1-0/',
        requires_replication: true,
        wdl_files: bigwig_wdl_files,
        wdl_task_name: 'macs2_signal_track_pooled',
      },
      {
        dcc_step_run: 'tf-chip-seq-pseudoreplicated-idr-step-v-1',
        dcc_step_version: '/analysis-step-versions/tf-chip-seq-pseudoreplicated-idr-step-v-1-0/',
        wdl_files: IdrWdlFiles(self.wdl_task_name),
        wdl_task_name: 'idr_pr',
      },
      {
        dcc_step_run: 'tf-chip-seq-pooled-pseudoreplicated-idr-step-v-1',
        dcc_step_version: '/analysis-step-versions/tf-chip-seq-pooled-pseudoreplicated-idr-step-v-1-0/',
        requires_replication: true,
        wdl_files: IdrWdlFiles(self.wdl_task_name, callbacks=['maybe_preferred_default']),
        wdl_task_name: 'idr_ppr',
      },
      {
        dcc_step_run: 'tf-chip-seq-replicated-idr-step-v-1',
        dcc_step_version: '/analysis-step-versions/tf-chip-seq-replicated-idr-step-v-1-0/',
        requires_replication: true,
        wdl_files: IdrWdlFiles(self.wdl_task_name, callbacks=['maybe_preferred_default', 'maybe_conservative_set']),
        wdl_task_name: 'idr',
      },
      {
        dcc_step_run: 'tf-chip-seq-pseudoreplicated-idr-ranked-peaks-file-format-conversion-step-v-1',
        dcc_step_version: '/analysis-step-versions/tf-chip-seq-pseudoreplicated-idr-ranked-peaks-file-format-conversion-step-v-1-0/',
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name,),
        wdl_task_name: 'idr_pr',
      },
      {
        dcc_step_run: 'tf-chip-seq-pooled-pseudoreplicated-idr-thresholded-peaks-file-format-conversion-step-v-1',
        dcc_step_version: '/analysis-step-versions/tf-chip-seq-pooled-pseudoreplicated-idr-thresholded-peaks-file-format-conversion-step-v-1-0/',
        requires_replication: true,
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, callbacks=['maybe_preferred_default'],),
        wdl_task_name: 'idr_ppr',
      },
      {
        dcc_step_run: 'tf-chip-seq-replicated-idr-thresholded-peaks-file-format-conversion-step-v-1',
        dcc_step_version: '/analysis-step-versions/tf-chip-seq-replicated-idr-thresholded-peaks-file-format-conversion-step-v-1-0/',
        requires_replication: true,
        wdl_files: FormatConversionWdlFiles(
          self.wdl_task_name,
          callbacks=[
            'maybe_conservative_set',
            'maybe_preferred_default',
          ],
        ),
        wdl_task_name: 'idr',
      },
    ],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  local HistoneMintPeakCallSteps(blacklist_derived_from_task='', blacklist_derived_from_filekey='blacklist') = {
    local has_blacklist_derived_from_task = std.length(blacklist_derived_from_task) > 0,
    local shared_file_props = {
      file_format_type: 'narrowPeak',
      quality_metrics: [
        'chip_replication',
        'chip_peak_enrichment',
      ],
    },
    local OverlapWdlFiles(blacklist_derived_from_task, blacklist_derived_from_filekey, output_type, callbacks=[],) = [
      (
        if std.length(callbacks) != 0 then { callbacks: callbacks } else {}
      ) + {
        derived_from_files: BedBigwigBlacklistDerivedFromFiles(blacklist_derived_from_task, blacklist_derived_from_filekey),
        file_format: 'bed',
        filekey: 'bfilt_overlap_peak',
        output_type: output_type,
      } + shared_file_props,
    ],
    local FormatConversionWdlFiles(derived_from_task, output_type, callbacks=[],) = [
      (
        if std.length(callbacks) != 0 then { callbacks: callbacks } else {}
      ) + {
        derived_from_files: [
          {
            derived_from_filekey: 'bfilt_overlap_peak',
            derived_from_task: derived_from_task,
          },
        ],
        file_format: 'bigBed',
        filekey: 'bfilt_overlap_peak_bb',
        output_type: output_type,
      } + shared_file_props,
    ],
    'accession.steps': [
      {
        dcc_step_run: 'histone-chip-signal-generation-step-v-1',
        dcc_step_version: '/analysis-step-versions/histone-chip-signal-generation-step-v-1-0/',
        wdl_files: bigwig_wdl_files,
        wdl_task_name: 'macs2_signal_track',
      },
      {
        dcc_step_run: 'histone-chip-seq-pooled-signal-generation-step-v-1',
        dcc_step_version: '/analysis-step-versions/histone-chip-seq-pooled-signal-generation-step-v-1-0/',
        requires_replication: true,
        wdl_files: bigwig_wdl_files,
        wdl_task_name: 'macs2_signal_track_pooled',
      },
      {
        local _blacklist_derived_from_task = if has_blacklist_derived_from_task then blacklist_derived_from_task else self.wdl_task_name,
        dcc_step_run: 'histone-chip-seq-pseudoreplicated-overlap-step-v-1',
        dcc_step_version: '/analysis-step-versions/histone-chip-seq-pseudoreplicated-overlap-step-v-1-0/',
        wdl_files: OverlapWdlFiles(_blacklist_derived_from_task, blacklist_derived_from_filekey, 'stable peaks'),
        wdl_task_name: 'overlap_pr',
      },
      {
        local _blacklist_derived_from_task = if has_blacklist_derived_from_task then blacklist_derived_from_task else self.wdl_task_name,
        dcc_step_run: 'histone-chip-seq-pooled-pseudoreplicated-overlap-step-v-1',
        dcc_step_version: '/analysis-step-versions/histone-chip-seq-pooled-pseudoreplicated-overlap-step-v-1-0/',
        requires_replication: true,
        wdl_files: OverlapWdlFiles(_blacklist_derived_from_task, blacklist_derived_from_filekey, 'stable peaks', callbacks=[
          'maybe_preferred_default',
        ],),
        wdl_task_name: 'overlap_ppr',
      },
      {
        local _blacklist_derived_from_task = if has_blacklist_derived_from_task then blacklist_derived_from_task else self.wdl_task_name,
        dcc_step_run: 'histone-chip-seq-replicated-overlap-step-v-1',
        dcc_step_version: '/analysis-step-versions/histone-chip-seq-replicated-overlap-step-v-1-0/',
        requires_replication: true,
        wdl_files: OverlapWdlFiles(_blacklist_derived_from_task, blacklist_derived_from_filekey, 'replicated peaks', callbacks=[
          'maybe_preferred_default',
        ],),
        wdl_task_name: 'overlap',
      },
      {
        dcc_step_run: 'histone-chip-seq-pseudoreplicated-overlap-stable-peaks-file-format-conversion-step-v-1',
        dcc_step_version: '/analysis-step-versions/histone-chip-seq-pseudoreplicated-overlap-stable-peaks-file-format-conversion-step-v-1-0/',
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, 'stable peaks'),
        wdl_task_name: 'overlap_pr',
      },
      {
        dcc_step_run: 'histone-chip-seq-pooled-pseudoreplicated-overlap-stable-peaks-file-format-conversion-step-v-1',
        dcc_step_version: '/analysis-step-versions/histone-chip-seq-pooled-pseudoreplicated-overlap-stable-peaks-file-format-conversion-step-v-1-0/',
        requires_replication: true,
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, 'stable peaks', callbacks=['maybe_preferred_default'],),
        wdl_task_name: 'overlap_ppr',
      },
      {
        dcc_step_run: 'histone-chip-seq-replicated-overlap-file-format-conversion-step-v-1',
        dcc_step_version: '/analysis-step-versions/histone-chip-seq-replicated-overlap-file-format-conversion-step-v-1-0/',
        requires_replication: true,
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, 'replicated peaks', callbacks=['maybe_preferred_default'],),
        wdl_task_name: 'overlap',
      },
    ],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'histone_chip_peak_call_only_steps.json': HistoneMintPeakCallSteps(),
  'mint_chip_peak_call_only_steps.json': HistoneMintPeakCallSteps(blacklist_derived_from_task='pool_blacklist', blacklist_derived_from_filekey='tas'),
  'tf_chip_steps.json': {
    'accession.steps': $['chip_map_only_steps.json']['accession.steps'] + $['tf_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'histone_chip_steps.json': {
    'accession.steps': $['chip_map_only_steps.json']['accession.steps'] + $['histone_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'mint_chip_steps.json': {
    'accession.steps': $['chip_map_only_steps.json']['accession.steps'] + $['mint_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
}
