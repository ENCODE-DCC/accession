import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from base64 import b64encode
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

import encode_utils

from accession.analysis import Analysis, MetaData
from accession.file import GSFile
from accession.helpers import MatchingMd5Record, PortalFileRecord, string_to_number
from accession.quality_metric import QualityMetric

ASSEMBLY = "assembly"
GENOME_ANNOTATION = "genome_annotation"


class AccessionSteps:
    def __init__(self, path_to_accession_step_json):
        self._path_to_accession_step_json = path_to_accession_step_json
        self._steps = None

    def _load_steps(self):
        if self._steps:
            return
        with open(self.path_to_json) as fp:
            self._steps = json.load(fp)

    @property
    def path_to_json(self):
        return self._path_to_accession_step_json

    @property
    def content(self):
        self._load_steps()
        return self._steps["accession.steps"]

    @property
    def raw_fastqs_keys(self) -> Optional[str]:
        self._load_steps()
        return self._steps.get("raw_fastqs_keys")


class Accession(ABC):
    """docstring for Accession
       Args:
        steps: AccessionSteps object
        analysis: Analysis object
        connection: Connection object
    """

    ASSEMBLIES = ["GRCh38", "mm10"]
    PROFILE_KEY = "_profile"

    def __init__(
        self,
        steps,
        analysis,
        connection,
        lab,
        award,
        log_file_path="accession.log",
        no_log_file=False,
    ):
        self.analysis = analysis
        self.steps = steps
        self.backend = self.analysis.backend
        self.conn = connection
        self.COMMON_METADATA = {"lab": lab, "award": award}
        self._dataset = None
        self.new_files = []
        self.new_qcs = []
        self.raw_qcs = []
        self._logger: Optional[logging.Logger] = None
        self._log_file_path = log_file_path
        self._no_log_file: bool = no_log_file

    @property
    def logger(self) -> logging.Logger:
        """
        Creates the instance's logger if it doesn't already exist, then returns the
        logger instance. Configured to log both to stderr (StreamHandler default) and to
        a log file.
        """
        if self._logger is None:
            logger = logging.getLogger(__name__)
            logger.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s"
            )

            stdout_handler = logging.StreamHandler(stream=sys.stdout)
            stdout_handler.setLevel(logging.DEBUG)
            stdout_handler.setFormatter(formatter)

            logger.addHandler(stdout_handler)

            eu_debug_logger = logging.getLogger(encode_utils.DEBUG_LOGGER_NAME)
            for hdlr in eu_debug_logger.handlers:
                eu_debug_logger.removeHandler(hdlr)
            eu_debug_logger.addHandler(stdout_handler)

            eu_post_logger = logging.getLogger(encode_utils.POST_LOGGER_NAME)
            for hdlr in eu_post_logger.handlers:
                eu_post_logger.removeHandler(hdlr)
            eu_post_logger.addHandler(stdout_handler)

            if not self._no_log_file:
                file_handler = logging.FileHandler(self._log_file_path)
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                eu_debug_logger.addHandler(file_handler)
                eu_post_logger.addHandler(file_handler)

            self._logger = logger
        return self._logger

    @property
    @abstractmethod
    def QC_MAP(self):
        raise NotImplementedError("Derived classes should provide their own QC_MAPs")

    def get_step_run_id(self, encode_file):
        step_run = encode_file.get("step_run")
        if isinstance(step_run, str):
            step_run_id = step_run
        elif isinstance(step_run, dict):
            step_run_id = step_run.get("@id")
        return step_run_id

    def get_all_encode_files_matching_md5_of_blob(
        self, file: GSFile
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves all files from the portal with an md5sum matching the blob's md5
        """
        md5sum = self.backend.md5sum(file)
        search_param = [("md5sum", md5sum), ("type", "File")]
        encode_files = self.conn.search(search_param)
        if not encode_files:
            return None
        return encode_files

    def get_encode_file_matching_md5_of_blob(self, file):
        """Finds an ENCODE File object whose md5sum matches md5 of a blob in URI in backend.

        Args:
            file (str): String representing an URI to an object in the backend.

        Returns:
            dict: Dictionary representation of the matching file object on portal
            None if no matching objects are found.
        """
        encode_files = self.get_all_encode_files_matching_md5_of_blob(file)
        if encode_files is None:
            return None
        filtered_encode_files = type(self).filter_encode_files_by_status(encode_files)
        if filtered_encode_files:
            if len(filtered_encode_files) > 1:
                self.logger.warning(
                    "get_encode_file_matching_md5_of_blob found more than 1 files matching the md5 of the blob."
                )
            return self.conn.get(filtered_encode_files[0].get("@id"))
        else:
            return None

    @staticmethod
    def filter_encode_files_by_status(
        encode_files, forbidden_statuses=("replaced", "revoked", "deleted")
    ):
        """Filter out files whose statuses are not allowed.

        From list of dicts representing encode file objects, filter out ones whose statuses are not allowed.

        Args:
            encode_files (list): List containing dicts representing encode file objects.
            forbidden_statuses (list): List of statuses. If file object has one of these statuses it will be filtered out.
            Statuses that encode file can have are: uploading, upload failed, in progress, released, archived, deleted, replaced,
            revoked, content error.

        Returns:
            list: List containing the dicts whose statuses are not contained in forbidden_statuses, empty list is possible.

        Raises:
            KeyError: If some of the files do not have status (this is an indication of an error on portal).
        """
        filtered_files = [
            file for file in encode_files if file["status"] not in forbidden_statuses
        ]
        return filtered_files

    def make_file_matching_md5_record(
        self, gs_file: GSFile
    ) -> Optional[MatchingMd5Record]:
        """
        Returns a record of all portal files with a matching md5sum, or None if no
        matching files were found.
        """
        matching = self.get_all_encode_files_matching_md5_of_blob(gs_file.filename)
        if not matching:
            return None
        portal_file_records = []
        for file in matching:
            portal_file_record = PortalFileRecord(
                file["@id"].split("/")[2], file["status"], file["dataset"]
            )
            portal_file_records.append(portal_file_record)
        matching_md5_record = MatchingMd5Record(
            gs_file_path=gs_file.filename, portal_files=portal_file_records
        )
        return matching_md5_record

    def raw_files_accessioned(self):
        for file in self.analysis.raw_fastqs:
            if not self.get_encode_file_matching_md5_of_blob(file.filename):
                return False
        return True

    def accession_file(self, encode_file, gs_file):
        file_exists = self.get_encode_file_matching_md5_of_blob(gs_file.filename)
        submitted_file_path = {"submitted_file_name": gs_file.filename}
        if file_exists:
            self.logger.warning(
                "Attempting to post duplicate file of %s with md5sum %s",
                file_exists.get("accession"),
                encode_file.get("md5sum"),
            )
        local_file = self.backend.download(gs_file.filename)[0]
        encode_file["submitted_file_name"] = local_file
        encode_posted_file = self.conn.post(encode_file)
        os.remove(local_file)
        encode_posted_file = self.patch_file(encode_posted_file, submitted_file_path)
        self.new_files.append(encode_posted_file)
        return encode_posted_file
        return file_exists

    def patch_file(self, encode_file, new_properties):
        new_properties[self.conn.ENCID_KEY] = encode_file.get("accession")
        return self.conn.patch(new_properties, extend_array_values=False)

    def log_if_exists(self, payload, profile_key):
        """
        If an object with given aliases already exists, as determined by an additional GET request,
        then log a warning before attempting to POST the payload. Truthiness of the dict returned by
        encode_utils.connection.Connection.get() is sufficient to check the object's existence on
        the portal, since it returns an empty dict when no matching record is found.
        """

        aliases = payload.get("aliases")
        if aliases:
            if self.conn.get(aliases, database=True):
                self.logger.error(
                    "%s with aliases %s already exists, will not post it",
                    profile_key.capitalize().replace("_", " "),
                    aliases,
                )

    def get_or_make_step_run(self, lab_prefix, run_name, step_version, task_name):
        """
        encode_utils.connection.Connection.post() does not fail on alias conflict, and does not
        expose the response status code, so we need to check for the existence of the object first
        before attempting to POST it with Accession.log_if_exists().
        """
        docker_tag = self.analysis.get_tasks(task_name)[0].docker_image.split(":")[1]
        aliases = [
            "{}:{}-{}-{}".format(
                lab_prefix, run_name, self.analysis.workflow_id, docker_tag
            )
        ]
        payload = {
            "aliases": aliases,
            "status": "in progress",
            "analysis_step_version": step_version,
        }
        profile_key = "analysis_step_runs"
        self.log_if_exists(payload, profile_key)
        payload[type(self).PROFILE_KEY] = profile_key
        return self.conn.post(payload)

    @property
    @abstractmethod
    def assembly(self):
        """
        A reminder that subclasses of Accession *must* provide their own implementation
        for assembly.
        """
        raise NotImplementedError(
            (
                "This method should be implemented by concrete derived classes specific to"
                " the pipeline in question."
            )
        )

    @property
    def genome_annotation(self):
        """
        Not every pipeline will strictly need this method, so the @abstractmethod
        decorator is not required as in the case of assembly, but we still need a
        default implementation to so that file_from_template can check if the annotation
        is there.
        """
        return None

    def find_portal_property_from_filekey(
        self, filekey: str, portal_property: str
    ) -> str:
        """
        Generic helper method that all pipelines can use to find the annotation
        """
        files = self.analysis.get_files(filekey=filekey)
        if files:
            annotation = self.get_encode_file_matching_md5_of_blob(files[0].filename)
            return annotation.get(portal_property, "")
        else:
            raise KeyError(
                "Could not find any file with key {} in metadata".format(filekey)
            )

    @property
    def lab_pi(self):
        return self.COMMON_METADATA["lab"].split("/labs/")[1].split("/")[0]

    @property
    def dataset(self):
        if self._dataset is None:
            self._dataset = self.get_encode_file_matching_md5_of_blob(
                self.analysis.raw_fastqs[0].filename
            ).get("dataset")
            return self._dataset
        else:
            return self._dataset

    @property
    def assay_term_name(self):
        return self.conn.get(self.dataset).get("assay_term_name")

    def get_number_of_biological_replicates(self):
        bio_reps = set(
            [
                rep.get("biological_replicate_number")
                for rep in self.conn.get(self.dataset).get("replicates")
            ]
        )
        return len(bio_reps)

    @property
    def is_replicated(self):
        return True if self.get_number_of_biological_replicates() > 1 else False

    def file_from_template(
        self,
        file,
        file_format,
        output_type,
        step_run,
        derived_from,
        dataset,
        file_format_type=None,
        extras: Optional[Dict[str, Any]] = None,
    ):
        """
        Note that extras are used to update the dictionary at the very end. This allows
        for callbacks to override properties like output_type that may have been
        specified in the template.
        """
        file_name = file.filename.split("gs://")[-1].replace("/", "-")
        obj = {
            "status": "uploading",
            "aliases": ["{}:{}".format(self.lab_pi, file_name)],
            "file_format": file_format,
            "output_type": output_type,
            "assembly": self.assembly,
            "dataset": dataset,
            "step_run": step_run.get("@id"),
            "derived_from": derived_from,
            "file_size": file.size,
            "md5sum": file.md5sum,
        }
        if file_format_type:
            obj["file_format_type"] = file_format_type
        if self.genome_annotation:
            obj["genome_annotation"] = self.genome_annotation
        if extras is not None:
            obj.update(extras)
        obj[type(self).PROFILE_KEY] = "file"
        obj.update(self.COMMON_METADATA)
        return obj

    def get_derived_from_all(self, file, files):
        ancestors = []
        for ancestor in files:
            ancestors.append(
                self.get_derived_from(
                    file,
                    ancestor.get("derived_from_task"),
                    ancestor.get("derived_from_filekey"),
                    ancestor.get("derived_from_output_type"),
                    ancestor.get("derived_from_inputs"),
                    ancestor.get("allow_empty"),
                    tuple(ancestor.get("disallow_tasks", ())),
                )
            )
        return list(set(self.flatten(ancestors)))

    def flatten(self, nested_list):
        if isinstance(nested_list, str):
            yield nested_list
        if isinstance(nested_list, list):
            for item in nested_list:
                yield from self.flatten(item)

    # Returns list of accession ids of files on portal or recently accessioned
    def get_derived_from(
        self,
        file,
        task_name,
        filekey,
        output_type=None,
        inputs=False,
        allow_empty=False,
        disallow_tasks: Tuple[str, ...] = (),
    ):
        try:
            derived_from_files = self.analysis.search_up(
                file.task, task_name, filekey, inputs, disallow_tasks=disallow_tasks
            )
        except ValueError:
            self.logger.error(
                "An error occured searching up for the parent file of %s",
                file.filename,
                exc_info=True,
            )
            raise
        encode_files = [
            self.get_encode_file_matching_md5_of_blob(gs_file.filename)
            for gs_file in derived_from_files
        ]
        accessioned_files = encode_files + self.new_files
        accessioned_files = [x for x in accessioned_files if x is not None]
        derived_from_accession_ids = []
        for gs_file in derived_from_files:
            for encode_file in accessioned_files:
                if gs_file.md5sum == encode_file.get("md5sum"):
                    # Optimal peaks can be mistaken for conservative peaks
                    # when their md5sum is the same
                    if output_type and output_type != encode_file.get("output_type"):
                        continue
                    derived_from_accession_ids.append(encode_file["@id"])
        derived_from_accession_ids = list(set(derived_from_accession_ids))

        # Raise exception when some or all of the derived_from files
        # are missing from the portal

        missing = "\n".join(
            [
                "{}: {}".format(filekey, filename)
                for filename in map(lambda x: x.filename, derived_from_files)
            ]
        )
        if not derived_from_accession_ids and not allow_empty:
            raise Exception(
                f"Missing all of the derived_from files on the portal: {missing}"
            )
        if len(derived_from_accession_ids) != len(derived_from_files):
            raise Exception(
                f"Missing some of the derived_from files on the portal: {missing}"
            )
        return derived_from_accession_ids

    # File object to be accessioned
    def make_file_obj(
        self,
        file,
        file_format,
        output_type,
        step_run,
        derived_from_files,
        file_format_type=None,
        callbacks: Optional[List[str]] = None,
    ):
        derived_from = self.get_derived_from_all(file, derived_from_files)
        extras: Dict[str, Any] = {}
        if callbacks:
            for callback in callbacks:
                result: Dict[str, Any] = getattr(self, callback)(file)
                extras.update(result)
        return self.file_from_template(
            file,
            file_format,
            output_type,
            step_run,
            derived_from,
            self.dataset,
            file_format_type,
            extras=extras,
        )

    def get_bio_replicate(self, encode_file, string=True):
        replicate = encode_file.get("biological_replicates")[0]
        if string:
            return str(replicate)
        return int(replicate)

    def post_qcs(self):
        for qc in self.raw_qcs:
            qc.payload.update({"quality_metric_of": qc.files})
            self.new_qcs.append(self.conn.post(qc.payload, require_aliases=False))

    def queue_qc(self, qc, encode_file, profile, shared=False):
        step_run_id = self.get_step_run_id(encode_file)
        qc.update({"step_run": step_run_id, "status": "in progress"})
        if self.assay_term_name:
            qc["assay_term_name"] = self.assay_term_name
        qc.update(self.COMMON_METADATA)
        qc[type(self).PROFILE_KEY] = profile
        # Shared QCs will have two or more file ids
        # under the 'quality_metric_of' property
        # and payload must be the same for all
        if shared:
            for item in self.raw_qcs:
                if item.payload == qc:
                    item.files.append(encode_file.get("@id"))
                    return
        self.raw_qcs.append(QualityMetric(qc, encode_file.get("@id")))

    def file_has_qc(self, encode_file, qc_name):
        if list(
            filter(lambda x: qc_name in x["@type"], encode_file["quality_metrics"])
        ):
            return True
        return False

    @staticmethod
    def encode_attachment_data(data):
        """
        Encodes the attachment data into a b64 datastring
        input: data as bytes object
        Output: data as string, encoded as b64
        """
        return b64encode(data).decode("utf-8")

    @staticmethod
    def make_download_link(filename, extension):
        return filename.split("/")[-1] + extension

    def make_attachment_object(self, contents, mime_type, filename, extension):
        attachment_object = {
            "type": mime_type,
            "download": self.make_download_link(filename, extension),
            "href": "data:{};base64,{}".format(
                mime_type, self.encode_attachment_data(contents)
            ),
        }
        return attachment_object

    def get_attachment(self, gs_file, mime_type, add_ext=""):
        """
        Files with certain extensions will fail portal validation since it can't guess
        the mime type correctly, e.g. a `.log` file with mime type `text/plain` will
        cause a schema validation error. We can trick the portal by appending a dummy
        extension that will cause the portal to correctly guess the mime type, for
        instance in the above case appending a `.txt` extension will validate properly.
        """
        filename = gs_file.filename
        contents = self.backend.read_file(filename)
        obj = self.make_attachment_object(contents, mime_type, filename, add_ext)
        return obj

    def accession_step(self, single_step_params, dry_run: bool = False):
        """
        Note that this method will attempt a getattr() when converting the qc method defined in the
        accessioning template to a function name. This will raise a NotImplementedError if the
        method is not defined, wrapping the AttributeError raised by getattr(). Quality metric
        helper functions should be implemented by derived classes.
        The optional parameter "requries_replication" is used to denote wdl tasks that
        will not be present in the metadata if the pipeline is ran on unreplicated data,
        for example pooled IDR in the ChIP-seq pipeline.
        """
        if single_step_params.get("requires_replication") is True:
            if not self.is_replicated:
                return
        if not dry_run:
            step_run = self.get_or_make_step_run(
                self.lab_pi,
                single_step_params["dcc_step_run"],
                single_step_params["dcc_step_version"],
                single_step_params["wdl_task_name"],
            )
            accessioned_files = []
        else:
            matching_records = []
        for task in self.analysis.get_tasks(single_step_params["wdl_task_name"]):
            for file_params in single_step_params["wdl_files"]:
                for wdl_file in [
                    file
                    for file in task.output_files
                    if file_params["filekey"] in file.filekeys
                ]:
                    if dry_run:
                        matching_record = self.make_file_matching_md5_record(wdl_file)
                        matching_records.append(matching_record)
                        continue
                    # Conservative IDR thresholded peaks may have
                    # the same md5sum as optimal one
                    try:
                        obj = self.make_file_obj(
                            wdl_file,
                            file_params["file_format"],
                            file_params["output_type"],
                            step_run,
                            file_params["derived_from_files"],
                            file_format_type=file_params.get("file_format_type"),
                            callbacks=file_params.get("callbacks"),
                        )
                        encode_file = self.accession_file(obj, wdl_file)
                    except Exception as e:
                        if "Conflict" in str(e) and file_params.get(
                            "possible_duplicate"
                        ):
                            continue
                        elif "Missing" in str(e):
                            raise
                        else:
                            self.logger.critical(
                                "An error occurred accessioning a file", exc_info=True
                            )
                            raise

                    # Parameter file inputted assumes Accession implements
                    # the methods to attach the quality metrics
                    quality_metrics = file_params.get("quality_metrics", [])
                    for qc in quality_metrics:
                        qc_method = getattr(self, type(self).QC_MAP[qc])
                        # Pass encode file with
                        # calculated properties
                        qc_method(
                            self.conn.get(encode_file.get("accession"), database=True),
                            wdl_file,
                        )
                    accessioned_files.append(encode_file)
        if dry_run:
            return matching_records
        return accessioned_files

    def accession_steps(self, dry_run: bool = False):
        if dry_run:
            self.logger.info("Currently in dry run mode, will NOT post to server.")
            accumulated_matches: List[Optional[MatchingMd5Record]] = []
            for step in self.steps.content:
                accumulated_matches.extend(self.accession_step(step, dry_run))
            self.report_dry_run(accumulated_matches)
        else:
            for step in self.steps.content:
                self.accession_step(step)
            self.post_qcs()

    def report_dry_run(self, records: List[Optional[MatchingMd5Record]]):
        """
        Print the report for the dry run. We use a format string to control the width
        for each column by adding padding where appropriate. The column width is
        governed by the length (in characters) of the longest element in each column.
        When there is more than one file at the portal that had a matching md5sum, the
        file path is not printed for subsequent report rows after the first match for
        visual clarity.

        Note that the match records are an Optional type, thus we need to remove Nones
        """
        header = (
            "File Path",
            "Matching Portal Files",
            "Portal Status",
            "Portal File Dataset",
        )
        matches = [i for i in records if i is not None]
        if not matches:
            self.logger.info("No MD5 conflicts found.")
            return
        else:
            self.logger.info(
                "Found files with duplicate md5sums at %s", self.conn.dcc_url
            )
        rows = [header]
        for match in matches:
            for i, portal_file in enumerate(match.portal_files):
                if i == 0:
                    display_filename = match.gs_file_path
                else:
                    display_filename = ""
                rows.append(
                    (
                        display_filename,
                        portal_file.accession,
                        portal_file.status,
                        portal_file.experiment,
                    )
                )
        columns = list(zip(*rows))
        column_widths = []
        for column in columns:
            lens = [len(i) for i in column]
            column_widths.append(max(lens))
        template = "{{:{}}} | {{:{}}} | {{:{}}} | {{:{}}}".format(*column_widths)
        for row in rows:
            msg = template.format(*row)
            self.logger.info(msg)


class AccessionGenericRna(Accession):
    def make_generic_correlation_qc(
        self,
        encode_file,
        gs_file,
        handler,
        qc_schema_name="CorrelationQualityMetric",
        qc_schema_name_with_hyphens="correlation-quality-metric",
    ):
        """
        Make correlation QC metrics in  a pipeline agnostic fashion. Pipeline specific logic is
        taken care of in the handler, the function that formats the qc metric dictionary.
        """
        if (
            self.file_has_qc(encode_file, qc_schema_name)
            or self.get_number_of_biological_replicates() != 2
        ):
            return
        qc = handler(gs_file)
        return self.queue_qc(qc, encode_file, qc_schema_name_with_hyphens, shared=True)


class AccessionBulkRna(AccessionGenericRna):
    QC_MAP = {
        "star_mapping_qc": "make_star_mapping_qc",
        "genome_flagstat_qc": "make_genome_flagstat_qc",
        "anno_flagstat_qc": "make_anno_flagstat_qc",
        "number_of_genes_detected_qc": "make_number_of_genes_detected_qc",
        "mad_qc_metric": "make_mad_qc_metric",
        "reads_by_gene_type_qc": "make_reads_by_gene_type_qc",
    }

    # These properties get added to the GeneTYpeQuantificationQualityMetric, this list needs to be in sync with the portal schema.
    # The rest will be available to the users via an attachment.
    GENE_TYPE_PROPERTIES = [
        "spikein",
        "rRNA",
        "Mt_rRNA",
        "miRNA",
        "protein_coding",
        "processed_transcript",
        "ribozyme",
        "sRNA",
        "scaRNA",
        "snRNA",
        "snoRNA",
        "antisense",
        "sense_overlapping",
        "sense_intronic",
    ]

    @property
    def assembly(self):
        filekey = "index"
        return self.find_portal_property_from_filekey(filekey, ASSEMBLY)

    @property
    def genome_annotation(self):
        filekey = "index"
        return self.find_portal_property_from_filekey(filekey, GENOME_ANNOTATION)

    @staticmethod
    def get_bytes_from_dict(input_dict: Dict, encoding: str = "utf-8") -> bytes:
        return json.dumps(input_dict).encode(encoding)

    def make_star_mapping_qc(self, encode_bam_file: Dict[str, Any], gs_file: GSFile):
        if self.file_has_qc(
            encode_bam_file, "StarQualityMetric"
        ):  # actual name of the object
            return
        qc_file = self.analysis.get_files(
            filename=gs_file.task.outputs["log_json"]  # task output name
        )[0]
        qc = self.backend.read_json(qc_file)
        star_qc_metric = qc.get("star_log_qc")  # what the key is in actual qc json file
        del star_qc_metric["Started job on"]
        del star_qc_metric["Started mapping on"]
        del star_qc_metric["Finished on"]
        for key, value in star_qc_metric.items():
            star_qc_metric[key] = string_to_number(value)
        qc_bytes = self.get_bytes_from_dict(qc)
        attachment = self.make_attachment_object(
            qc_bytes, "text/plain", qc_file.filename, ".txt"
        )
        star_qc_metric["attachment"] = attachment
        return self.queue_qc(
            star_qc_metric, encode_bam_file, "star-quality-metric"
        )  # backend mapping adding hyphens and removing caps

    def format_reads_by_gene_type_qc(self, qc_dict: Dict, properties_to_report: List) -> Dict:
        output = {prop: qc_dict[prop] for prop in properties_to_report}
        return output

    def make_reads_by_gene_type_qc(self, encode_file: Dict[str, Any], gs_file: GSFile):
        if self.file_has_qc(encode_file, "GeneTypeQuantificationQualityMetric"):
            return
        qc_file = self.analysis.search_down(gs_file.task, "rna_qc", "rnaQC")[0]
        qc = self.backend.read_json(qc_file)
        try:
            reads_by_gene_type_qc_metric = qc["gene_type_count"]
        except KeyError:
            self.logger.exception("Something is wrong with rna_qc file")
            raise
        output_qc = self.format_reads_by_gene_type_qc(
            reads_by_gene_type_qc_metric, self.GENE_TYPE_PROPERTIES
        )
        qc_bytes = self.get_bytes_from_dict(qc)
        attachment = self.make_attachment_object(
            qc_bytes, "text/plain", qc_file.filename, ".txt"
        )
        output_qc["attachment"] = attachment
        return self.queue_qc(
            output_qc, encode_file, "gene-type-quantification-quality-metric",
        )

    def make_qc_from_well_formed_json(
        self,
        encode_file: Dict[str, Any],
        gs_file: GSFile,
        qc_schema_name: str,
        qc_file_task_output_name: str,
        qc_dictionary_key: str,
        qc_schema_name_with_hyphens: str,
    ):
        if self.file_has_qc(encode_file, qc_schema_name):
            return
        qc_file = self.analysis.get_files(
            filename=gs_file.task.outputs[qc_file_task_output_name]
        )[0]
        qc = self.backend.read_json(qc_file)
        output_qc = qc.get(qc_dictionary_key)
        return self.queue_qc(output_qc, encode_file, qc_schema_name_with_hyphens)

    def make_flagstat_qc(
        self,
        encode_file: Dict[str, Any],
        gs_file: GSFile,
        task_output_name: str,
        qc_dictionary_key: str,
        convert_to_string: List = ["mapped_pct", "paired_properly_pct", "singletons_pct"],
    ):
        if self.file_has_qc(encode_file, "SamtoolsFlagstatsQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=gs_file.task.outputs[task_output_name]
        )[0]
        qc = self.backend.read_json(qc_file)
        output_qc = qc.get(qc_dictionary_key)
        for key in convert_to_string:
            # paired_properly_pct and singletons_pct are not there in single-ended
            try:
                output_qc[key] = str(output_qc[key])
            except KeyError:
                continue

        qc_bytes = self.get_bytes_from_dict(qc)
        attachment = self.make_attachment_object(
            qc_bytes, "text/plain", qc_file.filename, ".txt"
        )
        output_qc["attachment"] = attachment
        return self.queue_qc(
            output_qc, encode_file, "samtools-flagstats-quality-metric"
        )

    def make_genome_flagstat_qc(self, encode_file: Dict[str, Any], gs_file: GSFile):
        self.make_flagstat_qc(
            encode_file, gs_file, "genome_flagstat_json", "samtools_genome_flagstat"
        )

    def make_anno_flagstat_qc(self, encode_file: Dict[str, Any], gs_file: GSFile):
        self.make_flagstat_qc(
            encode_file, gs_file, "anno_flagstat_json", "samtools_anno_flagstat"
        )

    def make_number_of_genes_detected_qc(self, encode_file: Dict[str, Any], gs_file: GSFile):
        self.make_qc_from_well_formed_json(
            encode_file,
            gs_file,
            "GeneQuantificationQualityMetric",
            "number_of_genes",
            "number_of_genes_detected",
            "gene-quantification-quality-metric",
        )

    def make_mad_qc_metric(self, encode_file: Dict[str, Any], gs_file: GSFile):
        self.make_generic_correlation_qc(
            encode_file,
            gs_file,
            self.prepare_mad_qc_metric,
            "MadQualityMetric",
            "mad-quality-metric",
        )

    def prepare_mad_qc_metric(self, gs_file: GSFile) -> Dict:
        qc_file = self.analysis.search_down(gs_file.task, "mad_qc", "madQCmetrics")[0]
        qc = self.backend.read_json(qc_file)
        try:
            mad_qc = qc["MAD.R"]
        except KeyError:
            self.logger.exception("Something is wrong with the madqc source file")
            raise
        attachment_file = self.analysis.search_down(
            gs_file.task, "mad_qc", "madQCplot"
        )[0]
        attachment = self.get_attachment(attachment_file, "image/png")
        mad_qc["attachment"] = attachment
        return mad_qc


class AccessionLongReadRna(AccessionGenericRna):
    QC_MAP = {
        "long_read_rna_mapping": "make_long_read_rna_mapping_qc",
        "long_read_rna_quantification": "make_long_read_rna_quantification_qc",
        "long_read_rna_correlation": "make_long_read_rna_correlation_qc",
    }

    @property
    def assembly(self):
        filekey = "annotation_gtf"
        return self.find_portal_property_from_filekey(filekey, ASSEMBLY)

    @property
    def genome_annotation(self):
        filekey = "annotation_gtf"
        return self.find_portal_property_from_filekey(filekey, GENOME_ANNOTATION)

    def make_long_read_rna_correlation_qc(self, encode_file, gs_file):
        """
        Make and post Spearman QC for long read RNA by giving the make_generic_correlation_qc the
        appropriate handler.
        """
        return self.make_generic_correlation_qc(
            encode_file, gs_file, handler=self.prepare_long_read_rna_correlation_qc
        )

    def prepare_long_read_rna_correlation_qc(self, gs_file):
        """
        Handler for creating the correlation QC object, specifically for long read rna. Finds and
        parses the spearman QC JSON.
        """
        qc_file, *_ = self.analysis.search_down(
            gs_file.task, "calculate_spearman", "spearman"
        )
        qc = self.backend.read_json(qc_file)
        spearman_value = qc["replicates_correlation"]["spearman_correlation"]
        spearman_correlation_qc = {"Spearman correlation": spearman_value}
        return spearman_correlation_qc

    def make_long_read_rna_mapping_qc(self, encode_file, gs_file):
        """
        The commented lines add number_of_mapped_reads to the qc object, a field that is currently
        not valid under the schema.
        """
        if self.file_has_qc(encode_file, "LongReadRnaMappingQualityMetric"):
            return
        qc_file = self.analysis.get_files(filename=gs_file.task.outputs["mapping_qc"])[
            0
        ]
        qc = self.backend.read_json(qc_file)
        output_qc = {}
        mr = "mapping_rate"
        flnc = qc["full_length_non_chimeric_reads"]["flnc"]
        output_qc["full_length_non_chimeric_read_count"] = int(flnc)
        output_qc[mr] = float(qc[mr][mr])
        return self.queue_qc(
            output_qc, encode_file, "long-read-rna-mapping-quality-metric"
        )

    def make_long_read_rna_quantification_qc(self, encode_file, gs_file):
        if self.file_has_qc(encode_file, "LongReadRnaQuantificationQualityMetric"):
            return
        ngd = "number_of_genes_detected"
        qc_file = self.analysis.get_files(filename=gs_file.task.outputs[ngd])[0]
        qc = self.backend.read_json(qc_file)
        output_qc = {"genes_detected": int(qc[ngd][ngd])}
        return self.queue_qc(
            output_qc, encode_file, "long-read-rna-quantification-quality-metric"
        )


class AccessionMicroRna(AccessionGenericRna):
    QC_MAP = {
        "mirna_mapping": "make_microrna_mapping_qc",
        "mirna_quantification": "make_microrna_quantification_qc",
        "mirna_correlation": "make_microrna_correlation_qc",
        "star": "make_star_qc_metric",
    }

    @property
    def assembly(self):
        filekey = "annotation"
        return self.find_portal_property_from_filekey(filekey, ASSEMBLY)

    @property
    def genome_annotation(self):
        filekey = "annotation"
        return self.find_portal_property_from_filekey(filekey, GENOME_ANNOTATION)

    def make_microrna_quantification_qc(self, encode_file, gs_file):
        if self.file_has_qc(encode_file, "MicroRnaQuantificationQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=gs_file.task.outputs["star_qc_json"]
        )[0]
        qc = self.backend.read_json(qc_file)
        expressed_mirnas_qc = qc["expressed_mirnas"]
        return self.queue_qc(
            expressed_mirnas_qc, encode_file, "micro-rna-quantification-quality-metric"
        )

    def make_microrna_mapping_qc(self, encode_file, gs_file):
        if self.file_has_qc(encode_file, "MicroRnaMappingQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=gs_file.task.outputs["star_qc_json"]
        )[0]
        qc = self.backend.read_json(qc_file)
        aligned_reads_qc = qc["aligned_reads"]
        return self.queue_qc(
            aligned_reads_qc, encode_file, "micro-rna-mapping-quality-metric"
        )

    def make_microrna_correlation_qc(self, encode_file, gs_file):
        """
        Returns without queueing this QC for posting if the experiment is not replicated, since
        correlation is computed between pairs of replicates.
        """
        if (
            self.file_has_qc(encode_file, "CorrelationQualityMetric")
            or self.get_number_of_biological_replicates() != 2
        ):
            return
        qc_file = self.analysis.search_down(
            gs_file.task, "spearman_correlation", "spearman_json"
        )[0]
        qc = self.backend.read_json(qc_file)
        spearman_value = qc["spearman_correlation"]["spearman_correlation"]
        spearman_correlation_qc = {"Spearman correlation": spearman_value}
        return self.queue_qc(
            spearman_correlation_qc,
            encode_file,
            "correlation-quality-metric",
            shared=True,
        )

    def make_star_qc_metric(self, encode_bam_file, gs_file):
        if self.file_has_qc(encode_bam_file, "StarQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=gs_file.task.outputs["star_qc_json"]
        )[0]
        qc = self.backend.read_json(qc_file)
        star_qc_metric = qc.get("star_qc_metric")
        del star_qc_metric["Started job on"]
        del star_qc_metric["Started mapping on"]
        del star_qc_metric["Finished on"]
        for key, value in star_qc_metric.items():
            star_qc_metric[key] = string_to_number(value)
        return self.queue_qc(star_qc_metric, encode_bam_file, "star-quality-metric")


class AccessionChip(Accession):
    QC_MAP = {
        "chip_alignment": "make_chip_alignment_qc",
        "chip_align_enrich": "make_chip_align_enrich_qc",
        "chip_library": "make_chip_library_qc",
        "chip_replication": "make_chip_replication_qc",
        "chip_peak_enrichment": "make_chip_peak_enrichment_qc",
    }

    @property
    def assembly(self):
        files = self.analysis.get_files(filekey="ref_fa")
        if files:
            portal_index = self.get_encode_file_matching_md5_of_blob(files[0].filename)
        return portal_index["assembly"]

    @staticmethod
    def get_chip_pipeline_replication_method(qc: Dict[str, Any]) -> str:
        """
        Checks the qc report for the pipeline type and returns the appropriate
        reproducibility criteria, `idr` when using SPP peak caller and `overlap` if the
        peak caller was MACS2.
        """
        peak_caller = qc["general"]["peak_caller"]
        if peak_caller == "macs2":
            return "overlap"
        return "idr"

    def get_chip_pipeline_replicate(self, gs_file):
        """
        Searches for the input fastq array corresponding to the ancestor input fastqs of the current
        file and returns the pipeline replicate number. We only need to check R1, since it will
        always be there in both the single and paired ended runs of the ChIP pipeline. We need this
        in order to be able to identify the correct QC in the QC JSON.
        """
        parent_fastqs = [
            file.filename
            for file in self.analysis.search_up(
                gs_file.task, "align", "fastqs_R1", inputs="true"
            )
        ]
        pipeline_rep = None
        for k, v in self.analysis.metadata["inputs"].items():
            if "fastqs" in k and "ctl" not in k:
                if sorted(v) == sorted(parent_fastqs):
                    pipeline_rep = k.split("_")[1]
                    break
        if not pipeline_rep:
            raise ValueError(
                "Could not determine pipeline replicate number for file {}".format(
                    gs_file
                )
            )
        return pipeline_rep

    def maybe_preferred_default(self, gs_file: GSFile) -> Dict[str, bool]:
        """
        For replicated ChIP-seq experiment, the exact file that is to be labeled with
        preferred_default=true may vary. As such, this callback is registered for any
        file that might need to have this value set in the steps JSON, and called at
        file object generation time (make_file_obj) to fill in (or not) the missing
        value.
        """
        qc = self.backend.read_json(self.analysis.get_files("qc_json")[0])
        method = self.get_chip_pipeline_replication_method(qc)
        replication_qc = qc["replication"]["reproducibility"][method]

        optimal_set = replication_qc["opt_set"]
        current_set = gs_file.task.inputs["prefix"]
        if current_set == optimal_set:
            return {"preferred_default": True}
        return {}

    def maybe_conservative_set(self, gs_file: GSFile) -> Dict[str, str]:
        """
        For replicated ChIP-seq experiment, the exact file that is to be labeled as
        the conservative set may vary. As such, this callback is registered for any
        file that might need to have this value set in the steps JSON, and called at
        file object generation time (make_file_obj) to fill in (or not) the missing
        value.
        """
        qc = self.backend.read_json(self.analysis.get_files("qc_json")[0])[
            "replication"
        ]["reproducibility"]["idr"]

        consv_set = qc["consv_set"]
        current_set = gs_file.task.inputs["prefix"]
        if current_set == consv_set:
            return {"output_type": "conservative IDR thresholded peaks"}
        return {}

    def add_mapped_read_length(self, gs_file: GSFile) -> Dict[str, int]:
        """
        Obtains the value of mapped_read_length to post for bam files from the read
        length log in the ancestor align task in the ChIP-seq pipeline.
        """
        read_len_log = self.analysis.search_up(gs_file.task, "align", "read_len_log")[0]
        log_contents = self.backend.read_file(read_len_log.filename)
        try:
            mapped_read_length = int(log_contents)
        except ValueError as e:
            raise RuntimeError(
                f"Could not parse read length log into integer: tried to parse {log_contents}"
            ) from e
        return {"mapped_read_length": mapped_read_length}

    def make_chip_alignment_qc(self, encode_file, gs_file):
        """
        This function typecasts to match the ENCODE schema. Trucated zero values could
        potentially be deserialized from the qc json as integers instead of floats.
        """
        if self.file_has_qc(encode_file, "ChipAlignmentQualityMetric"):
            return
        qc = self.backend.read_json(self.analysis.get_files("qc_json")[0])
        replicate = self.get_chip_pipeline_replicate(gs_file)
        file_output_type = encode_file.get("output_type")
        if "unfiltered" in file_output_type:
            qc_key, processing_stage = "samstat", "unfiltered"
        else:
            qc_key, processing_stage = "nodup_samstat", "filtered"
        output_qc = qc["align"][qc_key][replicate]
        for k, v in output_qc.items():
            if k.startswith("pct"):
                output_qc[k] = float(v)
            else:
                output_qc[k] = int(v)
        # Add after to avoid trying to cast
        output_qc["processing_stage"] = processing_stage
        return self.queue_qc(
            output_qc, encode_file, "chip-alignment-samstat-quality-metric"
        )

    def make_chip_align_enrich_qc(self, encode_file, gs_file):
        """
        The xcor plots are not downstream of encode_file, in fact, they don't even share
        a common parent task with encode_file. Instead, we search up to find the parent
        align task of the current filtered bam, find the corresponding align_R1 task
        with the same fastq input, and search downstream from there for the xcor plot.
        """
        if self.file_has_qc(encode_file, "ChipAlignmentEnrichmentQualityMetric"):
            return
        qc = self.backend.read_json(self.analysis.get_files("qc_json")[0])
        replicate = self.get_chip_pipeline_replicate(gs_file)
        key_to_match = "fastqs_R1"
        parent_fastqs = [
            file.filename
            for file in self.analysis.search_up(
                gs_file.task, "align", key_to_match, inputs="true"
            )
        ]
        align_r1_tasks = self.analysis.get_tasks("align_R1")
        start_task = [
            i for i in align_r1_tasks if i.inputs[key_to_match] == parent_fastqs
        ]
        if len(start_task) != 1:
            raise ValueError(
                (
                    f"Incorrect number of candidate start tasks with {key_to_match}: "
                    f"expected 1 but found {start_task}"
                )
            )
        cross_corr_plot_pdf = self.analysis.search_down(
            start_task[0], "xcor", "plot_pdf"
        )[0]
        fingerprint_plot_png = self.analysis.search_down(gs_file.task, "jsd", "plot")[0]
        gc_bias_plot_png = self.analysis.search_down(
            gs_file.task, "gc_bias", "gc_plot"
        )[0]
        output_qc = {
            **qc["align_enrich"]["xcor_score"][replicate],
            **qc["align_enrich"]["jsd"][replicate],
        }
        # Typecasting to match ENCODE schema
        for k, v in output_qc.items():
            if k in [
                "argmin_corr",
                "estimated_fragment_len",
                "phantom_peak",
                "subsampled_reads",
            ]:
                output_qc[k] = int(v)
            else:
                output_qc[k] = float(v)
        output_qc.update(
            {
                "cross_correlation_plot": self.get_attachment(
                    cross_corr_plot_pdf, "application/pdf"
                ),
                "jsd_plot": self.get_attachment(fingerprint_plot_png, "image/png"),
                "gc_bias_plot": self.get_attachment(gc_bias_plot_png, "image/png"),
            }
        )
        return self.queue_qc(
            output_qc, encode_file, "chip-alignment-enrichment-quality-metric"
        )

    def make_chip_library_qc(self, encode_file, gs_file):
        if self.file_has_qc(encode_file, "ChipLibraryQualityMetric"):
            return
        qc = self.backend.read_json(self.analysis.get_files("qc_json")[0])
        replicate = self.get_chip_pipeline_replicate(gs_file)
        output_qc = {
            **qc["align"]["dup"][replicate],
            **qc["lib_complexity"]["lib_complexity"][replicate],
        }
        # Typecasting to match ENCODE schema
        for k, v in output_qc.items():
            if k in ["NRF", "PBC1", "PBC2", "pct_duplicate_reads"]:
                output_qc[k] = float(v)
            else:
                output_qc[k] = int(v)
        return self.queue_qc(output_qc, encode_file, "chip-library-quality-metric")

    def make_chip_replication_qc(self, encode_file, gs_file):
        """
        Rescue ratio and self-consistency ratio are only reported for optimal set. This
        set is determined by checking the QC JSON, and comparing to the prefix in the
        IDR task input in the WDL.
        The value of the QC's `reproducible_peaks` depends on the replicates or
        psuedo-replicates being compared.
        IDR cutoff, plot, and log are always reported for all IDR thresholded peaks
        files. They are not reported for the histone pipeline, which uses overlap.
        The IDR log file attachment is fudged with a .txt extension so that the portal
        can guess the mime type correctly and accept the file as valid.
        """
        if self.file_has_qc(encode_file, "ChipReplicationQualityMetric"):
            return
        raw_qc = self.backend.read_json(self.analysis.get_files("qc_json")[0])
        method = self.get_chip_pipeline_replication_method(raw_qc)
        qc = raw_qc["replication"]["reproducibility"][method]

        optimal_set = qc["opt_set"]
        current_set = gs_file.task.inputs["prefix"]
        output_qc = {}

        if current_set == optimal_set:
            output_qc.update(
                {
                    k: v
                    for k, v in qc.items()
                    if k
                    in ["rescue_ratio", "self_consistency_ratio", "reproducibility"]
                }
            )

        task_name = gs_file.task.task_name
        num_peaks = None
        if task_name == f"{method}_ppr":
            num_peaks = qc["Np"]
        elif task_name in ["idr", "overlap"]:
            num_peaks = qc["Nt"]
        elif task_name == f"{method}_pr":
            rep_num = current_set.split("-")[0][-1]
            num_peaks = qc[f"N{rep_num}"]
        if num_peaks is not None:
            output_qc["reproducible_peaks"] = int(num_peaks)

        if method == "idr":
            output_qc["idr_cutoff"] = float(gs_file.task.inputs["idr_thresh"])
            idr_plot_png = self.analysis.get_files(
                filename=gs_file.task.outputs["idr_plot"]
            )[0]
            idr_log = self.analysis.get_files(filename=gs_file.task.outputs["idr_log"])[
                0
            ]
            output_qc.update(
                {"idr_dispersion_plot": self.get_attachment(idr_plot_png, "image/png")}
            )
            output_qc.update(
                {
                    "idr_parameters": self.get_attachment(
                        idr_log, "text/plain", add_ext=".txt"
                    )
                }
            )
        return self.queue_qc(output_qc, encode_file, "chip-replication-quality-metric")

    def make_chip_peak_enrichment_qc(self, encode_file, gs_file):
        """
        The peak region stats are only useful for the optimal set, since the ones for
        rep1 and rep2 are applicable to files that are not posted by to the portal.
        IDR frip scores are applicable to any pair undergoing IDR, so they are always
        looked for.
        """
        if self.file_has_qc(encode_file, "ChipPeakEnrichmentQualityMetric"):
            return

        qc = self.backend.read_json(self.analysis.get_files("qc_json")[0])
        method = self.get_chip_pipeline_replication_method(qc)

        optimal_set = qc["replication"]["reproducibility"][method]["opt_set"]
        current_set = gs_file.task.inputs["prefix"]

        output_qc = {
            "frip": qc["peak_enrich"]["frac_reads_in_peaks"][method][current_set][
                "frip"
            ]
        }
        if current_set == optimal_set:
            output_qc.update({**qc["peak_stat"]["peak_region_size"][f"{method}_opt"]})
        for k, v in output_qc.items():
            if k in ["mean", "frip"]:
                output_qc[k] = float(v)
            else:
                output_qc[k] = int(v)
        return self.queue_qc(
            output_qc, encode_file, "chip-peak-enrichment-quality-metric"
        )


def accession_factory(
    pipeline_type: str, accession_metadata: str, *args, **kwargs
) -> Accession:
    """
    Matches against the user-specified pipeline_type string and returns an instance of
    the appropriate accession subclass. Usage of this factory has the nice effect of
    automatically supplying the appropriate AccessionSteps based on the pipeline name.
    """
    pipeline_type_map = {
        "bulk_rna": AccessionBulkRna,
        "mirna": AccessionMicroRna,
        "long_read_rna": AccessionLongReadRna,
        "chip_map_only": AccessionChip,
        "tf_chip_peak_call_only": AccessionChip,
        "histone_chip_peak_call_only": AccessionChip,
    }
    selected_accession: Optional[Type[Accession]] = None
    try:
        selected_accession = pipeline_type_map[pipeline_type]
    except KeyError as e:
        pipeline_type_options = ", ".join(pipeline_type_map.keys())
        raise RuntimeError(
            f"Could not find pipeline type {pipeline_type}: valid options are {pipeline_type_options}"
        ) from e
    current_dir = Path(__file__).resolve()
    steps_json_path = (
        current_dir.parents[1] / "accession_steps" / f"{pipeline_type}_steps.json"
    )
    accession_steps = AccessionSteps(steps_json_path)
    metadata = MetaData(accession_metadata)
    backend = kwargs.pop("backend", None)
    analysis = Analysis(
        metadata, raw_fastqs_keys=accession_steps.raw_fastqs_keys, backend=backend
    )
    return selected_accession(accession_steps, analysis, *args, **kwargs)
