{
  local MAYBE_PREFERRED_DEFAULT = 'maybe_preferred_default',
  local BedBigwigDerivedFromFiles(is_atac=false, ignore_pooled_peak_for_clarity=false) = [
    local disallow_call_peak_pooled = if !ignore_pooled_peak_for_clarity then [] else ['call_peak_pooled'];
    local disallow_choose_ctl = if is_atac then [] else ['choose_ctl'];
    local disallow_tasks = disallow_call_peak_pooled + disallow_choose_ctl;
    local disallow_tasks_value = if std.length(disallow_tasks) > 0 then { disallow_tasks: disallow_tasks } else {};
    {
      derived_from_filekey: 'nodup_bam',
      derived_from_task: 'filter',
    } + disallow_tasks_value,
  ] + (if is_atac then [] else [{
         derived_from_filekey: 'bam',
         derived_from_inputs: true,
         derived_from_task: 'bam2ta_ctl',
       }]),

  /* We insert the blacklist into the middle of the list so the array order is the same
  as the existing templates */
  local BedBigwigBlacklistDerivedFromFiles(
    blacklist_derived_from_task,
    derived_from_filekey='blacklist',
    is_atac=false,
    ignore_pooled_peak_for_clarity=false,
  ) = [BedBigwigDerivedFromFiles(is_atac, ignore_pooled_peak_for_clarity)[0]] + [{
    derived_from_filekey: derived_from_filekey,
    derived_from_inputs: true,
    derived_from_task: blacklist_derived_from_task,
  }] + (if is_atac then [] else [BedBigwigDerivedFromFiles(is_atac, ignore_pooled_peak_for_clarity)[1]]),
  local BigwigWdlFiles(is_atac=false) = [
    {
      derived_from_files: BedBigwigDerivedFromFiles(is_atac),
      file_format: 'bigWig',
      filekey: 'pval_bw',
      output_type: 'signal p-value',
      quality_metrics: [],
    },
    {
      derived_from_files: BedBigwigDerivedFromFiles(is_atac),
      file_format: 'bigWig',
      filekey: 'fc_bw',
      output_type: 'fold change over control',
      quality_metrics: [],
    },
  ],
  local AtacChipMapOnlySteps(
    is_control=false,
    is_atac=false,
    separate_control_task=false,
    pbam=false,
  ) = {
    local step_run = if is_atac then 'atac-seq-alignment-step-v-2' else 'chip-seq-alignment-step-v-2',
    local step_version =
      if is_atac then '/analysis-step-versions/atac-seq-alignment-step-v-2-1/'
      else if pbam then '/analysis-step-versions/chip-seq-alignment-step-v-2-1/'
      else '/analysis-step-versions/chip-seq-alignment-step-v-2-0/',
    local unfiltered_bam = {
      dcc_step_run: step_run,
      dcc_step_version: step_version,
      wdl_files: [
        {
          callbacks: [
            'add_mapped_read_length',
            'add_mapped_run_type',
          ] + (if !is_atac then [
                 'maybe_add_cropped_read_length',
                 'maybe_add_cropped_read_length_tolerance',
               ] else []),
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
          quality_metrics: (if is_atac then ['atac_alignment'] else [
                              'chip_alignment',
                            ]),
        },
      ],
      wdl_task_name: if separate_control_task then 'align_ctl' else 'align',
    },
    local unfiltered_bam_wrapped = if pbam then [] else [unfiltered_bam],
    'accession.steps': unfiltered_bam_wrapped + [
      {
        dcc_step_run: step_run,
        dcc_step_version: step_version,
        wdl_files: [
          {
            callbacks: [
              'add_mapped_read_length',
              'add_mapped_run_type',
            ] + (if !is_atac then [
                   'maybe_add_cropped_read_length',
                   'maybe_add_cropped_read_length_tolerance',
                 ] else []),
            // Python-style array comprension syntax
            local atac_filtered_bam_derived_from_files = [
              {
                derived_from_filekey: filekey,
                derived_from_inputs: true,
                derived_from_task: 'annot_enrich',
                should_search_down: true,
              }
              for filekey in ['blacklist', 'dnase', 'enh', 'prom']
            ] + [{
              derived_from_filekey: 'tss',
              derived_from_inputs: true,
              derived_from_task: 'tss_enrich',
              should_search_down: true,
            }] + atac_map_only_steps['accession.steps'][0].wdl_files[0].derived_from_files,
            derived_from_files: (if is_atac then atac_filtered_bam_derived_from_files else $['chip_map_only_steps.json']['accession.steps'][0].wdl_files[0].derived_from_files),
            file_format: 'bam',
            filekey: 'nodup_bam',
            output_type: if pbam then 'redacted alignments' else 'alignments',
            quality_metrics: (if is_atac then ['atac_alignment', 'atac_library', 'atac_align_enrich'] else [
                                'chip_alignment',
                              ] + (if !is_control then ['chip_align_enrich'] else []) + [
                                'chip_library',
                              ]),
          },
        ],
        wdl_task_name: if separate_control_task then 'filter_ctl' else 'filter',
      },
    ],
    raw_fastqs_keys: [
      'fastqs_R1',
      'fastqs_R2',
    ],
  },
  local AtacTfChipPeakCallOnlySteps(is_atac=false) = {
    local step_prefix = if is_atac then 'atac' else 'tf-chip',
    // Need a separate prefix for signal generation because TF ChIP signal generation
    // steps do not include `-seq`
    local signal_generation_prefix = if is_atac then 'atac-seq' else 'tf-chip',
    local file_format_type = 'narrowPeak',
    local shared_file_props_no_qc = {
      file_format_type: file_format_type,
      output_type: 'IDR thresholded peaks',
    },
    local shared_file_props = shared_file_props_no_qc {
      quality_metrics: (if is_atac then ['atac_replication', 'atac_peak_enrichment'] else [
                          'chip_replication',
                          'chip_peak_enrichment',
                        ]),
    },
    local IdrWdlFiles(
      blacklist_derived_from_task,
      callbacks=[],
      is_atac=false,
      ignore_pooled_peak_for_clarity=false,
    ) = [
      {
        derived_from_files: BedBigwigDerivedFromFiles(is_atac),
        file_format: 'bed',
        file_format_type: 'idr_ranked_peak',
        filekey: 'idr_unthresholded_peak',
        output_type: 'IDR ranked peaks',
        quality_metrics: [],
      },
      (
        if std.length(callbacks) != 0 then { callbacks: callbacks } else {}
      ) + {
        derived_from_files: BedBigwigBlacklistDerivedFromFiles(
          blacklist_derived_from_task,
          is_atac=is_atac,
          ignore_pooled_peak_for_clarity=ignore_pooled_peak_for_clarity,
        ),
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
      } + shared_file_props_no_qc,
    ],
    'accession.steps': [
      {
        dcc_step_run: '%s-signal-generation-step-v-1' % signal_generation_prefix,
        dcc_step_version: '/analysis-step-versions/%s-signal-generation-step-v-1-0/' % signal_generation_prefix,
        wdl_files: BigwigWdlFiles(is_atac),
        wdl_task_name: 'macs2_signal_track',
      },
      {
        dcc_step_run: '%s-pooled-signal-generation-step-v-1' % signal_generation_prefix,
        dcc_step_version: '/analysis-step-versions/%s-pooled-signal-generation-step-v-1-0/' % signal_generation_prefix,
        requires_replication: true,
        wdl_files: BigwigWdlFiles(is_atac),
        wdl_task_name: 'macs2_signal_track_pooled',
      },
      {
        dcc_step_run: '%s-seq-pseudoreplicated-idr-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-pseudoreplicated-idr-step-v-1-0/' % step_prefix,
        local callbacks = if is_atac then [] else [MAYBE_PREFERRED_DEFAULT],
        wdl_files: IdrWdlFiles(self.wdl_task_name, callbacks=callbacks, is_atac=is_atac),
        wdl_task_name: 'idr_pr',
      },
      {
        dcc_step_run: '%s-seq-pooled-pseudoreplicated-idr-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-pooled-pseudoreplicated-idr-step-v-1-0/' % step_prefix,
        requires_replication: true,
        local callbacks = if is_atac then [] else [MAYBE_PREFERRED_DEFAULT],
        wdl_files: IdrWdlFiles(self.wdl_task_name, callbacks=callbacks, is_atac=is_atac),
        wdl_task_name: 'idr_ppr',
      },
      {
        dcc_step_run: '%s-seq-replicated-idr-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-replicated-idr-step-v-1-0/' % step_prefix,
        requires_replication: true,
        local callbacks = (if is_atac then [] else [MAYBE_PREFERRED_DEFAULT]) + ['maybe_conservative_set'],
        wdl_files: IdrWdlFiles(self.wdl_task_name, callbacks=callbacks, is_atac=is_atac, ignore_pooled_peak_for_clarity=true),
        wdl_task_name: 'idr',
      },
      {
        dcc_step_run: '%s-seq-pseudoreplicated-idr-thresholded-peaks-file-format-conversion-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-pseudoreplicated-idr-thresholded-peaks-file-format-conversion-step-v-1-0/' % step_prefix,
        local callbacks = if is_atac then [] else [MAYBE_PREFERRED_DEFAULT],
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, callbacks=callbacks,),
        wdl_task_name: 'idr_pr',
      },
      {
        dcc_step_run: '%s-seq-pooled-pseudoreplicated-idr-thresholded-peaks-file-format-conversion-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-pooled-pseudoreplicated-idr-thresholded-peaks-file-format-conversion-step-v-1-0/' % step_prefix,
        requires_replication: true,
        local callbacks = if is_atac then [] else [MAYBE_PREFERRED_DEFAULT],
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, callbacks=callbacks,),
        wdl_task_name: 'idr_ppr',
      },
      {
        dcc_step_run: '%s-seq-replicated-idr-thresholded-peaks-file-format-conversion-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-replicated-idr-thresholded-peaks-file-format-conversion-step-v-1-0/' % step_prefix,
        requires_replication: true,
        local callbacks = ['maybe_conservative_set'] + (if is_atac then [] else [MAYBE_PREFERRED_DEFAULT]),
        wdl_files: FormatConversionWdlFiles(
          self.wdl_task_name,
          callbacks=callbacks,
        ),
        wdl_task_name: 'idr',
      },
    ],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  local AtacHistoneMintPeakCallSteps(is_atac=false, blacklist_derived_from_task='', blacklist_derived_from_filekey='blacklist') = {
    local step_prefix = if is_atac then 'atac' else 'histone-chip',
    local has_blacklist_derived_from_task = std.length(blacklist_derived_from_task) > 0,
    local shared_file_props_no_qc = {
      file_format_type: 'narrowPeak',
    },
    local shared_file_props = shared_file_props_no_qc {
      quality_metrics: (if is_atac then ['atac_replication', 'atac_peak_enrichment'] else [
                          'chip_replication',
                          'chip_peak_enrichment',
                        ]),
    },
    local OverlapWdlFiles(
      blacklist_derived_from_task,
      blacklist_derived_from_filekey,
      output_type,
      callbacks=[],
      is_atac=false,
      ignore_pooled_peak_for_clarity=false,
    ) = [
      (
        if std.length(callbacks) != 0 then { callbacks: callbacks } else {}
      ) + {
        derived_from_files: BedBigwigBlacklistDerivedFromFiles(
          blacklist_derived_from_task,
          blacklist_derived_from_filekey,
          is_atac=is_atac,
          ignore_pooled_peak_for_clarity=ignore_pooled_peak_for_clarity,
        ),
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
      } + shared_file_props_no_qc,
    ],
    'accession.steps': (if is_atac then [] else [
                          {
                            dcc_step_run: '%s-signal-generation-step-v-1' % step_prefix,
                            dcc_step_version: '/analysis-step-versions/%s-signal-generation-step-v-1-0/' % step_prefix,
                            wdl_files: BigwigWdlFiles(),
                            wdl_task_name: 'macs2_signal_track',
                          },
                          {
                            dcc_step_run: '%s-seq-pooled-signal-generation-step-v-1' % step_prefix,
                            dcc_step_version: '/analysis-step-versions/%s-seq-pooled-signal-generation-step-v-1-0/' % step_prefix,
                            requires_replication: true,
                            wdl_files: BigwigWdlFiles(),
                            wdl_task_name: 'macs2_signal_track_pooled',
                          },
                        ]) + [
      {
        local _blacklist_derived_from_task = if has_blacklist_derived_from_task then blacklist_derived_from_task else self.wdl_task_name,
        dcc_step_run: '%s-seq-pseudoreplicated-overlap-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-pseudoreplicated-overlap-step-v-1-0/' % step_prefix,
        wdl_files: OverlapWdlFiles(_blacklist_derived_from_task, blacklist_derived_from_filekey, 'pseudoreplicated peaks', callbacks=[MAYBE_PREFERRED_DEFAULT], is_atac=is_atac),
        wdl_task_name: 'overlap_pr',
      },
      {
        local _blacklist_derived_from_task = if has_blacklist_derived_from_task then blacklist_derived_from_task else self.wdl_task_name,
        dcc_step_run: '%s-seq-pooled-pseudoreplicated-overlap-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-pooled-pseudoreplicated-overlap-step-v-1-0/' % step_prefix,
        requires_replication: true,
        wdl_files: OverlapWdlFiles(
          _blacklist_derived_from_task,
          blacklist_derived_from_filekey,
          'pseudoreplicated peaks',
          callbacks=[MAYBE_PREFERRED_DEFAULT],
          is_atac=is_atac,
        ),
        wdl_task_name: 'overlap_ppr',
      },
      {
        local _blacklist_derived_from_task = if has_blacklist_derived_from_task then blacklist_derived_from_task else self.wdl_task_name,
        dcc_step_run: '%s-seq-replicated-overlap-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-replicated-overlap-step-v-1-0/' % step_prefix,
        requires_replication: true,
        wdl_files: OverlapWdlFiles(
          _blacklist_derived_from_task,
          blacklist_derived_from_filekey,
          'replicated peaks',
          callbacks=[MAYBE_PREFERRED_DEFAULT],
          is_atac=is_atac,
          ignore_pooled_peak_for_clarity=true,
        ),
        wdl_task_name: 'overlap',
      },
      {
        dcc_step_run: '%s-seq-pseudoreplicated-overlap-stable-peaks-file-format-conversion-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-pseudoreplicated-overlap-stable-peaks-file-format-conversion-step-v-1-0/' % step_prefix,
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, 'pseudoreplicated peaks', callbacks=[MAYBE_PREFERRED_DEFAULT]),
        wdl_task_name: 'overlap_pr',
      },
      {
        dcc_step_run: '%s-seq-pooled-pseudoreplicated-overlap-stable-peaks-file-format-conversion-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-pooled-pseudoreplicated-overlap-stable-peaks-file-format-conversion-step-v-1-0/' % step_prefix,
        requires_replication: true,
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, 'pseudoreplicated peaks', callbacks=[MAYBE_PREFERRED_DEFAULT],),
        wdl_task_name: 'overlap_ppr',
      },
      {
        dcc_step_run: '%s-seq-replicated-overlap-file-format-conversion-step-v-1' % step_prefix,
        dcc_step_version: '/analysis-step-versions/%s-seq-replicated-overlap-file-format-conversion-step-v-1-0/' % step_prefix,
        requires_replication: true,
        wdl_files: FormatConversionWdlFiles(self.wdl_task_name, 'replicated peaks', callbacks=[MAYBE_PREFERRED_DEFAULT],),
        wdl_task_name: 'overlap',
      },
    ],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  local atac_map_only_steps = AtacChipMapOnlySteps(is_atac=true),
  local chip_pbam_map_only_steps = AtacChipMapOnlySteps(pbam=true),
  local atac_idr_peak_call_steps = AtacTfChipPeakCallOnlySteps(is_atac=true),
  local atac_overlap_peak_call_steps = AtacHistoneMintPeakCallSteps(is_atac=true),
  local control_chip_separate_control_task = AtacChipMapOnlySteps(is_control=true, separate_control_task=true),
  'chip_map_only_steps.json': AtacChipMapOnlySteps(),
  'control_chip_steps.json': AtacChipMapOnlySteps(is_control=true),
  'control_chip_pbam_steps.json': AtacChipMapOnlySteps(is_control=true, pbam=true),
  'tf_chip_peak_call_only_steps.json': AtacTfChipPeakCallOnlySteps(),
  'histone_chip_peak_call_only_steps.json': AtacHistoneMintPeakCallSteps(),
  'mint_chip_peak_call_only_steps.json': AtacHistoneMintPeakCallSteps(blacklist_derived_from_task='pool_blacklist', blacklist_derived_from_filekey='tas'),
  'tf_chip_steps.json': {
    'accession.steps': $['chip_map_only_steps.json']['accession.steps'] + $['tf_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'tf_chip_control_fastqs_steps.json': {
    'accession.steps': control_chip_separate_control_task['accession.steps'] + $['chip_map_only_steps.json']['accession.steps'] + $['tf_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'tf_chip_pbam_steps.json': {
    'accession.steps': chip_pbam_map_only_steps['accession.steps'] + $['tf_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'histone_chip_steps.json': {
    'accession.steps': $['chip_map_only_steps.json']['accession.steps'] + $['histone_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'histone_chip_pbam_steps.json': {
    'accession.steps': chip_pbam_map_only_steps['accession.steps'] + $['histone_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'mint_chip_steps.json': {
    'accession.steps': $['chip_map_only_steps.json']['accession.steps'] + $['mint_chip_peak_call_only_steps.json']['accession.steps'],
    raw_fastqs_keys: $['chip_map_only_steps.json'].raw_fastqs_keys,
  },
  'atac_steps.json': {
    'accession.steps': atac_map_only_steps['accession.steps'] + atac_idr_peak_call_steps['accession.steps'] + atac_overlap_peak_call_steps['accession.steps'],
    raw_fastqs_keys: atac_map_only_steps.raw_fastqs_keys,
  },
}
