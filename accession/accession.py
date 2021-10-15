import logging
from abc import ABC, abstractmethod
from http import HTTPStatus
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
)

import boto3
from boto3.s3.transfer import TransferConfig
from encode_utils.connection import Connection
from qc_utils.parsers import (
    parse_flagstats,
    parse_hotspot1_spot_score,
    parse_picard_duplication_metrics,
    parse_samtools_stats,
)
from requests.exceptions import HTTPError

from accession.accession_steps import (
    AccessionStep,
    AccessionSteps,
    DerivedFromFile,
    FileParams,
)
from accession.analysis import Analysis
from accession.backends import Backend, LocalBackend, backend_factory
from accession.cloud_tasks import (
    AwsCredentials,
    AwsS3Object,
    CloudTasksUploadClient,
    QueueInfo,
    UploadPayload,
)
from accession.database.models import (
    DbFile,
    QualityMetric,
    Run,
    RunStatus,
    WorkflowLabel,
)
from accession.encode_models import (
    EncodeAnalysis,
    EncodeAttachment,
    EncodeCommonMetadata,
    EncodeDocument,
    EncodeDocumentType,
    EncodeExperiment,
    EncodeFile,
    EncodeGenericObject,
    EncodeQualityMetric,
    EncodeStepRun,
    FileStatus,
)
from accession.file import File, GSFile, S3File
from accession.helpers import (
    AbstractRecorder,
    LruCache,
    PreferredDefaultFilePatch,
    Recorder,
    flatten,
    get_bucket_and_key_from_s3_uri,
    impersonate_file,
    string_to_number,
)
from accession.logger_factory import logger_factory
from accession.metadata import Metadata, metadata_factory
from accession.preflight import MatchingMd5Record, PreflightHelper

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
    from mypy_boto3_s3.type_defs import CopySourceTypeDef

BOTO3_DEFAULT_MULTIPART_CHUNKSIZE = 8_388_608
BOTO3_MULTIPART_MAX_PARTS = 10_000


class Accession(ABC):
    """
    Shared base class for pipeline-specific subclasses. Cannot be used directly, must
    use derived classes with concrete implementations of abstractmethods like assembly.
    """

    def __init__(
        self,
        steps: AccessionSteps,
        analysis: Analysis,
        connection: Connection,
        common_metadata: EncodeCommonMetadata,
        recorder: AbstractRecorder,
        log_file_path: str = "accession.log",
        no_log_file: bool = False,
        queue_info: Optional[QueueInfo] = None,
        private_filenames: bool = False,
    ) -> None:
        self.analysis = analysis
        self.steps = steps
        self.conn = connection
        self.common_metadata = common_metadata
        self.recorder = recorder
        self.new_files: List[EncodeFile] = []
        self.upload_queue: List[Tuple[EncodeFile, File]] = []
        self.new_qcs: List[EncodeQualityMetric] = []
        self.raw_qcs: List[EncodeQualityMetric] = []
        self.log_file_path = log_file_path
        self.no_log_file = no_log_file
        self.private_filenames = private_filenames
        # keys are hex md5sums, values are lists of portal objects
        self.search_cache: LruCache[str, List[Dict[str, Any]]] = LruCache()
        self.preferred_default_file_patches: Dict[str, PreferredDefaultFilePatch] = {}
        self._logger: Optional[logging.Logger] = None
        self._experiment: Optional[EncodeExperiment] = None
        self._preflight_helper: Optional[PreflightHelper] = None

        self.cloud_tasks_upload_client: Optional[CloudTasksUploadClient] = None
        if queue_info is not None:
            self.cloud_tasks_upload_client = CloudTasksUploadClient(
                queue_info=queue_info,
                log_file_path=log_file_path,
                no_log_file=no_log_file,
            )

    @property
    @abstractmethod
    def assembly(self) -> str:
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
    @abstractmethod
    def QC_MAP(self) -> Dict[str, str]:
        raise NotImplementedError("Derived classes should provide their own QC_MAPs")

    @property
    def genome_annotation(self) -> Optional[str]:
        """
        Not every pipeline will strictly need this method, so the @abstractmethod
        decorator is not required as in the case of assembly, but we still need a
        default implementation to so that file_from_template can check if the annotation
        is there.
        """
        return None

    @property
    def pipeline_version(self) -> str:
        """
        Pulls the pipeline version out of the submitted WDL workflow's `meta` section,
        works for most pipelines. Strips leading `v` character to satisfy portal regex,
        needed for DNAse and the RNA pipelines.
        """
        return (
            self.analysis.metadata.get_parsed_workflow()
            .workflow.meta["version"]
            .lstrip("v")
        )

    @property
    def logger(self) -> logging.Logger:
        """
        Creates the instance's logger if it doesn't already exist, then returns the
        logger instance. Configured to log both to stderr (StreamHandler default) and to
        a log file.
        """
        if self._logger is None:
            logger = logger_factory(__name__, self.log_file_path, self.no_log_file)
            self._logger = logger
        return self._logger

    @property
    def preflight_helper(self) -> PreflightHelper:
        if self._preflight_helper is None:
            self._preflight_helper = PreflightHelper(self.logger)
        return self._preflight_helper

    @property
    def experiment(self) -> EncodeExperiment:
        if self._experiment is None:
            encode_file = self.get_encode_file_matching_md5_of_blob(
                self.analysis.raw_fastqs[0]
            )
            if encode_file is None:
                raise ValueError("Could not find raw fastqs on the portal")
            experiment_obj = self.conn.get(encode_file.dataset, frame="embedded")
            self._experiment = EncodeExperiment(experiment_obj)
        return self._experiment

    @abstractmethod
    def preferred_default_should_be_updated(
        self, qc_value: Union[int, float], current_best_qc_value: Union[int, float]
    ) -> bool:
        """
        Should return a value if the current file is has a qc value that is "better"
        than the current best file, otherwise should return None.
        """
        raise NotImplementedError

    @abstractmethod
    def get_preferred_default_qc_value(self, file: File) -> Union[int, float]:
        """
        Returns the QC value to judge whether or not the given file should be
        `preferred_default`.
        """
        raise NotImplementedError

    def get_all_encode_files_matching_md5_of_blob(
        self, file: File
    ) -> Optional[List[EncodeFile]]:
        """
        Retrieves all files from the portal with an md5sum matching the blob's md5. Will
        always attempt to use cached results. We need to search with frame=embedded so
        that the portal will return the full file objects, otherwise they will return
        with an arbitrary frame that does not include even the md5sum.
        """
        file_md5sum = file.md5sum
        search_param = [
            ("md5sum", file_md5sum),
            ("type", "File"),
            ("frame", "embedded"),
        ]
        cache_result = self.search_cache.get(file_md5sum)
        # Handle cache miss
        if cache_result is None:
            self.logger.debug(
                "Could not retrive search result from cache for md5sum %s will search portal",
                file_md5sum,
            )
            encode_files = self.conn.search(search_param)
            self.search_cache.insert(file_md5sum, encode_files)
        else:
            self.logger.debug(
                "Will use cached search result for file with md5sum %s", file_md5sum
            )
            encode_files = cache_result
        if not encode_files:
            return None
        modeled_encode_files = [EncodeFile(file_props) for file_props in encode_files]
        return modeled_encode_files

    def get_encode_file_matching_md5_of_blob(self, file: File) -> Optional[EncodeFile]:
        """Finds an ENCODE File object whose md5sum matches md5 of a blob in URI in backend.

        Args:
            file (File): A File representing an object on the backend.

        Returns:
            EncodeFile: an instance of EncodeFile, a document-object mapping
            None if no matching objects are found.
        """
        encode_files = self.get_all_encode_files_matching_md5_of_blob(file)
        if encode_files is None:
            return None
        filtered_encode_files = EncodeFile.filter_encode_files_by_status(encode_files)
        if filtered_encode_files:
            if len(filtered_encode_files) > 1:
                self.logger.warning(
                    "get_encode_file_matching_md5_of_blob found more than 1 files matching the md5 of the blob."
                )
            return filtered_encode_files[0]
        else:
            return None

    def make_file_matching_md5_record(self, file: File) -> Optional[MatchingMd5Record]:
        """
        This has not been completely extracted into preflight.py because otherwise the
        preflight helper would be required to know about the method
        `get_all_encode_files_matching_md5_of_blob`.
        """
        matching = self.get_all_encode_files_matching_md5_of_blob(file)
        if matching is None:
            return None
        record = self.preflight_helper.make_file_matching_md5_record(
            file.filename, matching
        )
        return record

    def raw_files_accessioned(self) -> bool:
        for file in self.analysis.raw_fastqs:
            if not self.get_encode_file_matching_md5_of_blob(file):
                return False
        return True

    def accession_file(self, encode_file: Dict[str, Any], file: File) -> EncodeFile:
        """
        First POSTs the file metadata and subsequently queues upload of the actual data.
        The file is queued for upload if there are no 409 conflicts for the posted file
        metadata. In addition, if there is a conflict and the file has a status of
        "upload failed", then reupload will be queued. If there is a 409 conflict and
        the file status is uploading, then we assume the file is currently being
        uploaded and upload will not be queued.
        """
        file_exists = self.get_encode_file_matching_md5_of_blob(file)
        if file_exists:
            self.logger.warning(
                "Attempting to post duplicate file of %s with md5sum %s",
                file_exists.get("accession"),
                encode_file.get("md5sum"),
            )
        encode_posted_file, status_code = self.conn.post(
            encode_file,
            upload_file=False,
            return_original_status_code=True,
            truncate_long_strings_in_payload_log=True,
        )
        modeled_encode_file = EncodeFile(encode_posted_file)
        if modeled_encode_file.status == FileStatus.UploadFailed or (
            modeled_encode_file.status == FileStatus.Uploading
            and status_code != HTTPStatus.CONFLICT
        ):
            self.upload_queue.append((modeled_encode_file, file))
        else:
            self.logger.info(
                "Encode file %s is already uploaded, will not reupload",
                modeled_encode_file.at_id,
            )
        self.new_files.append(modeled_encode_file)
        return modeled_encode_file

    def upload_file(self, encode_file: EncodeFile, file: File) -> None:
        """
        If there is a Cloud Tasks upload client (i.e. successfully read the config from
        the environment) then will upload using Cloud Tasks, otherwise will fallback
        to local file upload if the file is on Google Cloud Storage.
        """
        if isinstance(file, S3File):
            self._upload_file_s3_to_s3(encode_file, file)
            return
        if self.cloud_tasks_upload_client is None:
            self.logger.info(
                (
                    "Could not find Cloud Tasks client (is the environment configured "
                    "correctly?), will use local upload"
                )
            )
            self._upload_file_locally(encode_file, file)
            return

        if not isinstance(file, GSFile):
            raise ValueError("Cannot upload local files via Cloud Tasks")
        self._upload_file_using_cloud_tasks(encode_file, file)

    def _get_s3_client_and_credentials(
        self, encode_file: EncodeFile
    ) -> "Tuple[S3Client,Dict[str,str]]":
        credentials = self.conn.regenerate_aws_upload_creds(encode_file.accession)
        client = boto3.client(
            "s3",
            aws_access_key_id=credentials["access_key"],
            aws_secret_access_key=credentials["secret_key"],
            aws_session_token=credentials["session_token"],
        )
        return client, credentials

    def _get_s3_transfer_config(self, file_size: int) -> TransferConfig:
        multipart_chunksize = self._calculate_multipart_chunksize(file_size)
        transfer_config = TransferConfig(multipart_chunksize=multipart_chunksize)
        return transfer_config

    def _upload_file_s3_to_s3(self, encode_file: EncodeFile, s3_file: S3File) -> None:
        """
        The S3 client `copy` works about as well as AWS CLI, should expect ~150 MB/s
        copy speed on a decent connection. Requires that the ENCODE AWS account have
        read access to the objects to be uploaded, this can be set in the bucket policy.
        """
        s3_client, credentials = self._get_s3_client_and_credentials(encode_file)
        destination_s3_uri = credentials["upload_url"]
        bucket, key = get_bucket_and_key_from_s3_uri(destination_s3_uri)
        transfer_config = self._get_s3_transfer_config(s3_file.size)
        copy_source: "CopySourceTypeDef" = {
            "Bucket": s3_file.bucket,
            "Key": s3_file.key,
        }
        self.logger.info(
            "Uploading file %s to %s", s3_file.filename, destination_s3_uri
        )
        s3_client.copy(
            Bucket=bucket, Key=key, CopySource=copy_source, Config=transfer_config
        )
        self.logger.info("Finished uploading file %s", s3_file.filename)

    def _upload_file_locally(self, encode_file: EncodeFile, file: File) -> None:
        """
        At a high level, uploads the file to S3 by streaming bytes. As the s3 client
        reads chunks they are lazily fetched from GCS. Blocks until upload is complete.
        Supports both GCS and S3 files as input.

        In more details, obtains STS credentials to upload to the portal file specified
        by `encode_file`, creates a s3 client, and uploads the file corresponding to
        `file` (potentially as multipart). For this to work, `file` must have a
        file-like `read` method. For more details see the `boto3` docs:
        https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.upload_fileobj

        Extensive testing revealed that for the boto3 default transfer config performed
        satisfactorily, see PIP-745
        """
        s3, credentials = self._get_s3_client_and_credentials(encode_file)
        s3_uri = credentials["upload_url"]
        bucket, key = get_bucket_and_key_from_s3_uri(s3_uri)
        transfer_config = self._get_s3_transfer_config(file.size)
        self.logger.info("Uploading file %s to %s", file.filename, s3_uri)
        s3.upload_fileobj(file, bucket, key, Config=transfer_config)  # type: ignore
        self.logger.info("Finished uploading file %s", file.filename)

    def _calculate_multipart_chunksize(self, file_size_bytes: int) -> int:
        """
        Calculates the `multipart_chunksize` to use for `boto3` `TransferConfig` to
        ensure that the file can be uploaded successfully without reaching the 100000
        part limit. The default values are the same as the defaults for `TransferConfig`
        """
        multipart_chunksize = BOTO3_DEFAULT_MULTIPART_CHUNKSIZE * (
            max((file_size_bytes - 1), 0)
            // (BOTO3_MULTIPART_MAX_PARTS * BOTO3_DEFAULT_MULTIPART_CHUNKSIZE)
            + 1
        )
        return multipart_chunksize

    def _upload_file_using_cloud_tasks(
        self, encode_file: EncodeFile, file: GSFile
    ) -> None:
        """
        Submits file for upload to the Cloud Tasks queue. Unlike `_upload_file_locally`
        this returns before the file upload completes, and returns when the task gets
        queued for upload.
        """
        if self.cloud_tasks_upload_client is None:
            raise ValueError("Missing Cloud Tasks client")
        credentials = self.conn.regenerate_aws_upload_creds(encode_file.accession)
        aws_credentials = AwsCredentials(
            aws_access_key_id=credentials["access_key"],
            aws_secret_access_key=credentials["secret_key"],
            aws_session_token=credentials["session_token"],
        )
        s3_uri = credentials["upload_url"]
        bucket, key = get_bucket_and_key_from_s3_uri(s3_uri)
        aws_s3_object = AwsS3Object(bucket=bucket, key=key)
        upload_payload = UploadPayload(
            aws_credentials=aws_credentials, aws_s3_object=aws_s3_object, gcs_blob=file
        )
        self.logger.info(
            "Submitting file %s for upload to %s using queue %s",
            file.filename,
            s3_uri,
            self.cloud_tasks_upload_client.get_queue_path(),
        )
        try:
            self.cloud_tasks_upload_client.upload(upload_payload)
        except Exception:
            self.logger.exception("Could not submit file for upload to Cloud Tasks")
            raise

    def get_or_make_step_run(self, accession_step: AccessionStep) -> EncodeStepRun:
        """
        encode_utils.connection.Connection.post() does not fail on alias conflict, here
        we log if there was a 409 conflict.
        """
        tasks = self.analysis.get_tasks(accession_step.wdl_task_name)
        if not tasks:
            error_message = (
                f"Could not find task {accession_step.wdl_task_name} in workflow."
            )
            if accession_step.requires_replication:
                error_message += (
                    "This step run requires the workflow to be replicated, you may "
                    "need to check that the number of replicates in the workflow "
                    "matches the number of replicates on the portal with a status in "
                    f"{EncodeExperiment.ALLOWED_REPLICATE_STATUSES}"
                )
            raise ValueError(error_message)
        docker_tag = tasks[0].docker_image
        aliases = [
            "{}:{}-{}-{}".format(
                self.common_metadata.lab_pi,
                accession_step.step_run,
                self.analysis.workflow_id,
                docker_tag.split(":")[1] if docker_tag is not None else "",
            )
        ]
        payload = EncodeStepRun.get_portal_object(
            aliases=aliases,
            common_metadata=self.common_metadata,
            step_version=accession_step.step_version,
        )
        posted, status_code = self.conn.post(
            payload,
            return_original_status_code=True,
            truncate_long_strings_in_payload_log=True,
        )
        posted, status_code = self.conn.post(payload, return_original_status_code=True)
        if status_code == HTTPStatus.CONFLICT:
            self.logger.warning(
                "Analysis step run with aliases %s already exists, will not post it",
                aliases,
            )
        return EncodeStepRun(posted)

    def find_portal_property_from_filekey(
        self, filekey: str, portal_property: str
    ) -> Union[Any, str]:
        """
        Generic helper method that all pipelines can use to find the annotation
        """
        files = self.analysis.get_files(filekey=filekey)
        msg = "Could not find any file with key {} in metadata".format(filekey)
        if files:
            annotation = self.get_encode_file_matching_md5_of_blob(files[0])
            if annotation is None:
                raise KeyError(msg)
            return annotation.get(portal_property, "")
        else:
            raise KeyError(msg)

    def get_derived_from_all(
        self, file: File, files: List[DerivedFromFile]
    ) -> List[str]:
        ancestors = []
        for ancestor in files:
            ancestors.append(self.get_derived_from(file, ancestor))
        return list(set(flatten(ancestors)))

    def get_derived_from(self, file: File, ancestor: DerivedFromFile) -> List[str]:
        """
        Returns list of accession ids of files on portal or recently accessioned. Will
        search_down if the ancestor file indicates it should be `search_down`ed for via
        its `should_search_down` property.

        Generally this searches the portal and looks through newly accessioned files to
        find the appropriate `derived_from` file. However, it is possible to avoid
        searching for files on the portal by specifing `"only_search_current_analysis": true`
        in the template. This is useful when there are several files with an md5sum that
        is the same as the parent file, but you know you only need to connect to the
        newly posted file.
        """
        task = file.get_task()
        try:
            if ancestor.should_search_down:
                derived_from_files = self.analysis.search_down(
                    task,
                    ancestor.derived_from_task,
                    ancestor.derived_from_filekey,
                    ancestor.derived_from_inputs,
                )
            else:
                derived_from_files = self.analysis.search_up(
                    task,
                    ancestor.derived_from_task,
                    ancestor.derived_from_filekey,
                    ancestor.derived_from_inputs,
                    disallow_tasks=ancestor.disallow_tasks,
                )
        except ValueError:
            self.logger.exception(
                "An error occurred searching for the parent file of %s", file.filename
            )
            raise

        # Do the filtering before getting md5sums to avoid unnecessary searches
        if ancestor.workflow_inputs_to_match:
            derived_from_files = self._filter_derived_from_files_by_workflow_inputs(
                derived_from_files, ancestor
            )

        derived_from_accession_ids = []
        if ancestor.only_search_current_analysis:
            for file in derived_from_files:
                for new_file in self.new_files:
                    if (new_file.md5sum == file.md5sum) and (
                        new_file.submitted_file_name == file.filename
                    ):
                        derived_from_accession_ids.append(new_file.at_id)
        else:
            encode_files = []
            for file in derived_from_files:
                encode_file = self.get_encode_file_matching_md5_of_blob(file)
                if encode_file is not None:
                    encode_files.append(encode_file)
            accessioned_files = encode_files + self.new_files
            for file in derived_from_files:
                for encode_file in accessioned_files:
                    if file.md5sum == encode_file.md5sum:
                        # Optimal peaks can be mistaken for conservative peaks
                        # when their md5sum is the same
                        if (
                            ancestor.derived_from_output_type is not None
                            and ancestor.derived_from_output_type
                            != encode_file.output_type
                        ):
                            continue
                        derived_from_accession_ids.append(encode_file.at_id)
        # Duplicate derived from files may be an indication of a problem
        # (or absolutely ok as is the case in bulk rna single ended runs)
        if len(set(derived_from_accession_ids)) != len(derived_from_accession_ids):
            self.logger.info(
                "Duplicated accession ids detected in derived_from_accession_ids: %s",
                " ".join(derived_from_accession_ids),
            )
        derived_from_accession_ids = list(set(derived_from_accession_ids))

        # Raise exception when some or all of the derived_from files
        # are missing from the portal

        missing = "\n".join(
            [
                "{}: {}".format(ancestor.derived_from_filekey, filename)
                for filename in map(lambda x: x.filename, derived_from_files)
            ]
        )
        if not derived_from_accession_ids and not ancestor.allow_empty:
            raise Exception(
                f"Missing all of the derived_from files on the portal: {missing}"
            )
        if len(derived_from_accession_ids) != len(derived_from_files):
            raise Exception(
                "Missing some of the derived_from files on the portal, found ids "
                f"{derived_from_accession_ids}, still missing {missing}"
            )
        return derived_from_accession_ids

    def _filter_derived_from_files_by_workflow_inputs(
        self, derived_from_files: List[File], ancestor: DerivedFromFile
    ) -> List[File]:
        """
        Filter the list of candidate derived_from files on the condition that the
        filename matches or is present in a workflow input. Used in
        `self.get_derived_from`
        """
        new = []
        potential_filenames = flatten(
            [
                self.analysis.metadata.content["inputs"][key]
                for key in ancestor.workflow_inputs_to_match
            ]
        )
        for file in derived_from_files:
            if file.filename in potential_filenames:
                new.append(file)
        return new

    def make_file_obj(
        self, file: File, file_params: FileParams, step_run: EncodeStepRun
    ) -> Dict[str, Any]:
        """
        Obtains a file object postable to the ENCODE portal. Slashes `/` are not allowed
        in the aliases, so the file URI can't directly be used as part of the alias.

        Furthermore, the workflow ID is prepended to the file alias so that even
        call-cached outputs will have unique aliases.
        """
        derived_from = self.get_derived_from_all(file, file_params.derived_from_files)
        extras: Dict[str, Any] = {}
        for callback in file_params.callbacks:
            result: Dict[str, Any] = getattr(self, callback)(file)
            extras.update(result)
        file_name = (
            file.get_filename_for_encode_alias()
            if not self.private_filenames
            else file.md5sum
        )
        obj = EncodeFile.from_template(
            aliases=[
                "{}:{}-{}".format(
                    self.common_metadata.lab_pi, self.analysis.workflow_id, file_name
                )
            ],
            assembly=self.assembly,
            common_metadata=self.common_metadata,
            dataset=self.experiment.at_id,
            derived_from=derived_from,
            file_params=file_params,
            file_size=file.size,
            file_md5sum=file.md5sum,
            step_run_id=step_run.at_id,
            submitted_file_name=file.filename if not self.private_filenames else None,
            genome_annotation=self.genome_annotation,
            extras=extras,
        )
        return obj

    def post_qcs(self) -> None:
        for qc in self.raw_qcs:
            posted_qc = self.conn.post(
                qc.get_portal_object(),
                require_aliases=False,
                truncate_long_strings_in_payload_log=True,
            )
            self.new_qcs.append(EncodeQualityMetric.from_portal_object(posted_qc))

    def queue_qc(
        self,
        qc: Dict[str, Any],
        encode_file: EncodeFile,
        profile: str,
        shared: bool = False,
    ) -> None:
        """
        Shared QCs will have two or more file ids under the 'quality_metric_of' property
        and payload must be the same for all.
        """
        qc.update(
            {
                "step_run": encode_file.step_run_id,
                "assay_term_name": self.experiment.assay_term_name,
                self.conn.PROFILE_KEY: profile,
                **self.common_metadata,
            }
        )
        modeled_qc: EncodeQualityMetric = EncodeQualityMetric.from_payload_and_file_id(
            qc, encode_file.at_id
        )
        if shared:
            for item in self.raw_qcs:
                if item.payload == modeled_qc.payload:
                    item.files.append(encode_file.at_id)
                    return
        self.raw_qcs.append(modeled_qc)

    def get_attachment(
        self, file: File, mime_type: str, additional_extension: str = ""
    ) -> Dict[str, str]:
        """
        Files with certain extensions will fail portal validation since it can't guess
        the mime type correctly, e.g. a `.log` file with mime type `text/plain` will
        cause a schema validation error. We can trick the portal by appending a dummy
        extension that will cause the portal to correctly guess the mime type, for
        instance in the above case appending a `.txt` extension will validate properly.
        """
        contents = file.read_bytes()
        attachment = EncodeAttachment(contents, file.filename)
        obj = attachment.get_portal_object(
            mime_type, additional_extension=additional_extension
        )
        return obj

    def post_document(self, document: EncodeDocument) -> EncodeGenericObject:
        """
        Returns an instance of `EncodeGenericObject` representing the posted document.
        If the document already exists, as determined by an alias conflict (409) then
        the document will not be posted and the existing document on the portal will be
        returned.
        """
        postable_document = document.get_portal_object()
        response, status_code = self.conn.post(
            postable_document,
            return_original_status_code=True,
            truncate_long_strings_in_payload_log=True,
        )
        posted_document = EncodeGenericObject(response)
        if status_code == HTTPStatus.CONFLICT:
            self.logger.warning(
                "Found existing document %s with conflicting aliases, could not post",
                posted_document.at_id,
            )
        return posted_document

    def post_analysis(self) -> EncodeGenericObject:
        """
        Tries to POST the new analysis. If an equivalent analysis exists, as determined
        by 409 conflict, then this will not POST anything. Will post the workflow
        metadata as an attachment in a document, then insert that document into the
        `documents` array in the analysis object, and finally post the analysis object.
        """
        documents = []
        if not self.private_filenames:
            document_aliases = [
                f"{self.common_metadata.lab_pi}:cromwell-metadata-{self.analysis.workflow_id}"
            ]
            document_attachment = self.analysis.metadata.get_as_attachment(
                filename_prefix=self.experiment.accession
            )
            document = EncodeDocument(
                attachment=document_attachment,
                common_metadata=self.common_metadata,
                document_type=EncodeDocumentType.WorkflowMetadata,
                aliases=document_aliases,
            )
            posted_document = self.post_document(document)
            documents = [posted_document]
        current_analysis = EncodeAnalysis(
            files=self.new_files,
            common_metadata=self.common_metadata,
            workflow_id=self.analysis.workflow_id,
            documents=documents,
            pipeline_version=self.pipeline_version,
            quality_standard=self.steps.quality_standard,
        )
        payload = current_analysis.get_portal_object()
        response, status_code = self.conn.post(
            payload,
            return_original_status_code=True,
            truncate_long_strings_in_payload_log=True,
        )
        modeled_analysis = EncodeGenericObject(response)
        if status_code == HTTPStatus.CONFLICT:
            self.logger.warning(
                "Found existing analysis %s with conflicting aliases, could not post",
                modeled_analysis.at_id,
            )
        return modeled_analysis

    def patch_experiment_internal_status(self) -> None:
        """
        Patches the internal_status of the experiment being accessioned to indicate
        accessioning has completed.
        """
        payload = self.experiment.get_patchable_internal_status()
        try:
            self.conn.patch(payload)
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
                self.logger.warning(
                    (
                        "Could not patch experiment internal status, this is normal for "
                        "non-admin users"
                    )
                )
                return
            raise e

    def patch_experiment_analyses(self, analysis: EncodeGenericObject) -> None:
        payload = self.experiment.get_patchable_analyses(analysis.at_id)
        self.conn.patch(payload, extend_array_values=True)

    def maybe_update_preferred_default_file_patches(
        self, file_params: FileParams, encode_file: EncodeFile, file: File
    ) -> None:
        """
        Checks if the current file should be the `preferred_default` and if adds it to
        the queue of patches to apply, displacing the file (if any) in the queue with
        the same `file_format`/`file_format_type`/`output_type` combination.
        """
        hash_key = f"{file_params.file_format}{file_params.file_format_type or ''}{file_params.output_type}"
        preferred_default_patch = self.preferred_default_file_patches.get(hash_key)
        current_best_qc_value = (
            None
            if preferred_default_patch is None
            else preferred_default_patch.qc_value
        )
        qc_value = self.get_preferred_default_qc_value(file)
        if current_best_qc_value is None or self.preferred_default_should_be_updated(
            qc_value, current_best_qc_value
        ):
            self.preferred_default_file_patches[hash_key] = PreferredDefaultFilePatch(
                at_id=encode_file.at_id, qc_value=qc_value
            )

    def patch_preferred_default_files(self) -> None:
        """
        Patches the files that should be `preferred_default`
        """
        for (
            preferred_default_file_patch
        ) in self.preferred_default_file_patches.values():
            payload = preferred_default_file_patch.get_portal_patch()
            self.conn.patch(payload)

    def record_run(self, run_status: RunStatus) -> None:
        workflow_labels = [
            WorkflowLabel(key=key, value=value)
            for key, value in self.analysis.metadata.get_filtered_labels().items()
        ]
        files = []
        for file in self.new_files:
            # Enum interpreted as string, so ignore types
            # https://github.com/dropbox/sqlalchemy-stubs/issues/114
            db_file = DbFile(  # type: ignore
                portal_at_id=file.at_id, status=file.status
            )
            file_qcs = []
            for qc in self.new_qcs:
                if qc.files is None:
                    raise ValueError(f"Could not determine files for QC {qc.at_id}")
                if file.at_id in qc.files:
                    # We know here that the QC has an ID, since we initialized the
                    # object with the response we got back from the portal on POST
                    qc_id = cast(str, qc.at_id)
                    file_qcs.append(QualityMetric(portal_at_id=qc_id))
            db_file.quality_metrics = file_qcs
            files.append(db_file)
        run = Run(  # type: ignore
            experiment_at_id=self.experiment.at_id,
            workflow_id=self.analysis.workflow_id,
            status=run_status,
            workflow_labels=workflow_labels,
            files=files,
        )
        self.recorder.record(run)

    def accession_step(
        self, single_step_params: AccessionStep, dry_run: bool = False
    ) -> Union[List[Optional[MatchingMd5Record]], List[EncodeFile], None]:
        """
        Note that this method will attempt a getattr() when converting the qc method defined in the
        accessioning template to a function name. This will raise a NotImplementedError if the
        method is not defined, wrapping the AttributeError raised by getattr(). Quality metric
        helper functions should be implemented by derived classes.
        The optional parameter "requires_replication" is used to denote wdl tasks that
        will not be present in the metadata if the pipeline is ran on unreplicated data,
        for example pooled IDR in the ChIP-seq pipeline.
        """
        if single_step_params.requires_replication:
            if not self.experiment.is_replicated:
                return None
        if not dry_run:
            step_run = self.get_or_make_step_run(single_step_params)
            accessioned_files: List[EncodeFile] = []
        else:
            matching_records: List[Optional[MatchingMd5Record]] = []
        for task in self.analysis.get_tasks(single_step_params.wdl_task_name):
            for file_params in single_step_params.wdl_files:
                for wdl_file in [
                    file
                    for file in task.output_files
                    if file_params.filekey in file.filekeys
                ]:
                    if dry_run:
                        matching_record = self.make_file_matching_md5_record(wdl_file)
                        matching_records.append(matching_record)
                        continue
                    try:
                        obj = self.make_file_obj(wdl_file, file_params, step_run)
                        encode_file = self.accession_file(obj, wdl_file)
                    except Exception as e:
                        if "Conflict" in str(e):
                            continue
                        else:
                            self.logger.exception(
                                "An error occurred accessioning a file"
                            )
                            raise e

                    if file_params.maybe_preferred_default:
                        self.maybe_update_preferred_default_file_patches(
                            file_params, encode_file, wdl_file
                        )
                    for qc in file_params.quality_metrics:
                        qc_method = getattr(self, type(self).QC_MAP[qc])  # type: ignore
                        qc_method(encode_file, wdl_file)
                    accessioned_files.append(encode_file)
        if dry_run:
            return matching_records
        return accessioned_files

    def _get_dry_run_matches(self) -> List[MatchingMd5Record]:
        """
        Performs a dry run accessioning and reports back files that would be posted that
        have md5 conflicts.
        """
        accumulated_matches: List[Optional[MatchingMd5Record]] = []
        for step in self.steps.content:
            step_matches = self.accession_step(step, dry_run=True)
            # Cast to silence mypy complaining about not handling all invariants in
            # the Union returned above
            step_matches = cast(
                Union[List[Optional[MatchingMd5Record]], None], step_matches
            )
            if step_matches is None:
                continue
            accumulated_matches.extend(step_matches)
        matches = [i for i in accumulated_matches if i is not None]
        return matches

    def accession_steps(self, dry_run: bool = False, force: bool = False) -> None:
        """
        First executes a dry run, checking for md5 duplicates. If `dry_run` is `True`
        or if duplicates were detected and `force_accession` is `False` then will
        return, otherwise the experiment will subsequently actually be accessioned.

        The main entrypoint for accessioning. The process looks like this:
            * For each step in the template, accession the step run, files, and generate
              the QCs
            * Post all the QCs generated in the previous step
            * Post the `Analysis` object pointing to all the files that were accessioned
              as part of the run
            * Update the experiment internal_status to indicate that the accessioning
              has completed
            * Upload all of the files to S3. We do this as the last step so that all of
              the metadata objects are posted quickly, which ideally allows them to fit
              within one Elasticsearch indexing cycle on the portal (1 minute)

        When `dry_run` is `True`, then the only thing we do is iterate through all of
        the steps and check for potential duplicates that would be posted in the normal
        mode, without posting, patching, or uploading anything.
        """
        self.logger.info("Currently performing dry run, will not post to server.")
        accumulated_matches = self._get_dry_run_matches()
        self.preflight_helper.report_dry_run(accumulated_matches)

        if dry_run:
            self.logger.info("Dry run finished")
            return

        if accumulated_matches:
            if not force:
                self.logger.critical(
                    "One or more md5 duplicates detected, stopping accessioning"
                )
                return

            self.logger.warning(
                (
                    "One or more md5 duplicates detected, but `--force` is set so "
                    "continuing accessioning"
                )
            )

        try:
            for step in self.steps.content:
                self.accession_step(step)
            self.patch_preferred_default_files()
            self.post_qcs()
            analysis = self.post_analysis()
            self.patch_experiment_analyses(analysis)
            for encode_file, file in self.upload_queue:
                self.upload_file(encode_file, file)
            self.patch_experiment_internal_status()
        except Exception:
            self.logger.exception("Failed to complete accessioning")
            self.record_run(run_status=RunStatus.Failed)
            raise
        else:
            self.record_run(run_status=RunStatus.Succeeded)


class AccessionGenericRna(Accession):
    def preferred_default_should_be_updated(
        self, qc_value: Union[float, int], current_best_qc_value: Union[float, int]
    ) -> bool:
        """
        All the RNA-pipelines compare values in the same way.
        """
        return qc_value > current_best_qc_value

    def get_preferred_default_qc_value(self, file: File) -> Union[float, int]:
        """
        Dummy implementation since we don't have preferred_default specs for different
        RNA pipelines yet.
        """
        return super().get_preferred_default_qc_value(file)

    def make_generic_correlation_qc(
        self,
        encode_file: EncodeFile,
        file: File,
        handler: Callable[[File], Dict[str, Any]],
        qc_schema_name: str = "CorrelationQualityMetric",
        qc_schema_name_with_hyphens: str = "correlation-quality-metric",
    ) -> None:
        """
        Make correlation QC metrics in  a pipeline agnostic fashion. Pipeline specific logic is
        taken care of in the handler, the function that formats the qc metric dictionary.
        """
        if (
            encode_file.has_qc(qc_schema_name)
            or self.experiment.get_number_of_biological_replicates() != 2
        ):
            return
        qc = handler(file)
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
    def assembly(self) -> str:
        filekey = "index"
        return self.find_portal_property_from_filekey(filekey, EncodeFile.ASSEMBLY)

    @property
    def genome_annotation(self) -> str:
        filekey = "index"
        return self.find_portal_property_from_filekey(
            filekey, EncodeFile.GENOME_ANNOTATION
        )

    def get_preferred_default_qc_value(self, file: File) -> Union[float, int]:
        mapping_qc_file = self.analysis.search_up(file.get_task(), "align", "log_json")[
            0
        ].read_json()
        return int(mapping_qc_file["star_log_qc"]["Uniquely mapped reads number"])

    def make_star_mapping_qc(self, encode_bam_file: EncodeFile, file: File) -> None:
        if encode_bam_file.has_qc("StarQualityMetric"):  # actual name of the object
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["log_json"]  # task output name
        )[0]
        qc = qc_file.read_json()
        star_qc_metric = qc["star_log_qc"]  # what the key is in actual qc json file
        del star_qc_metric["Started job on"]
        del star_qc_metric["Started mapping on"]
        del star_qc_metric["Finished on"]
        for key, value in star_qc_metric.items():
            star_qc_metric[key] = string_to_number(value)
        qc_bytes = EncodeAttachment.get_bytes_from_dict(qc)
        modeled_attachment = EncodeAttachment(qc_bytes, file.filename)
        attachment = modeled_attachment.get_portal_object(
            mime_type="application/json", additional_extension=".json"
        )
        star_qc_metric["attachment"] = attachment
        return self.queue_qc(
            star_qc_metric, encode_bam_file, "star-quality-metric", shared=True
        )  # backend mapping adding hyphens and removing caps

    def format_reads_by_gene_type_qc(
        self, qc_dict: Dict[str, Any], properties_to_report: List[str]
    ) -> Dict[str, Any]:
        output = {prop: qc_dict[prop] for prop in properties_to_report}
        return output

    def make_reads_by_gene_type_qc(self, encode_file: EncodeFile, file: File) -> None:
        if encode_file.has_qc("GeneTypeQuantificationQualityMetric"):
            return
        task = file.get_task()
        qc_file = self.analysis.search_down(task, "rna_qc", "rnaQC")[0]
        qc = qc_file.read_json()
        try:
            gene_type_count_key = "gene_type_count"
            reads_by_gene_type_qc_metric = qc[gene_type_count_key]
        except KeyError:
            self.logger.exception(
                "Could not find key %s in rna_qc file", gene_type_count_key
            )
            raise
        output_qc = self.format_reads_by_gene_type_qc(
            reads_by_gene_type_qc_metric, self.GENE_TYPE_PROPERTIES
        )
        qc_bytes = EncodeAttachment.get_bytes_from_dict(qc)
        modeled_attachment = EncodeAttachment(qc_bytes, file.filename)
        attachment = modeled_attachment.get_portal_object(
            mime_type="application/json", additional_extension=".json"
        )
        output_qc["attachment"] = attachment
        return self.queue_qc(
            output_qc, encode_file, "gene-type-quantification-quality-metric"
        )

    def make_qc_from_well_formed_json(
        self,
        encode_file: EncodeFile,
        file: File,
        qc_schema_name: str,
        qc_file_task_output_name: str,
        qc_dictionary_key: str,
        qc_schema_name_with_hyphens: str,
    ) -> None:
        if encode_file.has_qc(qc_schema_name):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs[qc_file_task_output_name]
        )[0]
        qc = qc_file.read_json()
        output_qc = qc[qc_dictionary_key]
        return self.queue_qc(output_qc, encode_file, qc_schema_name_with_hyphens)

    def make_flagstat_qc(
        self,
        encode_file: EncodeFile,
        file: File,
        task_output_name: str,
        qc_dictionary_key: str,
    ) -> None:

        convert_to_string = ("mapped_pct", "paired_properly_pct", "singletons_pct")
        if encode_file.has_qc("SamtoolsFlagstatsQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs[task_output_name]
        )[0]
        qc = qc_file.read_json()
        output_qc = qc[qc_dictionary_key]
        for key in convert_to_string:
            # paired_properly_pct and singletons_pct are not there in single-ended
            try:
                output_qc[key] = str(output_qc[key])
            except KeyError:
                continue

        qc_bytes = EncodeAttachment.get_bytes_from_dict(qc)
        modeled_attachment = EncodeAttachment(qc_bytes, file.filename)
        attachment = modeled_attachment.get_portal_object(
            mime_type="application/json", additional_extension=".json"
        )
        output_qc["attachment"] = attachment
        return self.queue_qc(
            output_qc, encode_file, "samtools-flagstats-quality-metric"
        )

    def make_genome_flagstat_qc(self, encode_file: EncodeFile, file: File) -> None:
        self.make_flagstat_qc(
            encode_file, file, "genome_flagstat_json", "samtools_genome_flagstat"
        )

    def make_anno_flagstat_qc(self, encode_file: EncodeFile, file: File) -> None:
        self.make_flagstat_qc(
            encode_file, file, "anno_flagstat_json", "samtools_anno_flagstat"
        )

    def make_number_of_genes_detected_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        self.make_qc_from_well_formed_json(
            encode_file,
            file,
            "GeneQuantificationQualityMetric",
            "number_of_genes",
            "number_of_genes_detected",
            "gene-quantification-quality-metric",
        )

    def prepare_mad_qc_metric(self, file: File) -> Dict[str, Any]:
        task = file.get_task()
        qc_file = self.analysis.search_down(task, "mad_qc", "madQCmetrics")[0]
        qc = qc_file.read_json()
        try:
            qc_key = "MAD.R"
            mad_qc = qc[qc_key]
        except KeyError:
            self.logger.exception("Could not find key %s in madqc source file", qc_key)
            raise
        attachment_file = self.analysis.search_down(task, "mad_qc", "madQCplot")[0]
        attachment = self.get_attachment(attachment_file, "image/png")
        mad_qc["attachment"] = attachment
        return mad_qc

    def make_mad_qc_metric(self, encode_file: EncodeFile, file: File) -> None:
        """
        Special logic is required to facilitate situation where the experiment is
        unreplicated in biological replication sense, but contains two technical replicates.
        In this situation from pipeline POV the experiment is replicated and thus madQC gets calculated.
        """
        if encode_file.has_qc("MadQualityMetric"):
            return

        num_biological_replicates = (
            self.experiment.get_number_of_biological_replicates()
        )
        if num_biological_replicates > 2:
            return
        elif (
            num_biological_replicates == 1
            and self.experiment.get_number_of_technical_replicates() == 2
        ) or num_biological_replicates == 2:
            mad_qc = self.prepare_mad_qc_metric(file)
            return self.queue_qc(mad_qc, encode_file, "mad-quality-metric", shared=True)
        else:
            return


class AccessionBulkRnaPbam(AccessionBulkRna):
    def make_star_mapping_qc(self, encode_bam_file: EncodeFile, file: File) -> None:
        if encode_bam_file.has_qc("StarQualityMetric"):  # actual name of the object
            return
        task = file.get_task()
        qc_file = self.analysis.search_up(
            task, "align", "log_json"  # task output name
        )[0]
        qc = qc_file.read_json()
        star_qc_metric = qc["star_log_qc"]  # what the key is in actual qc json file
        del star_qc_metric["Started job on"]
        del star_qc_metric["Started mapping on"]
        del star_qc_metric["Finished on"]
        del star_qc_metric["Deletion average length"]
        del star_qc_metric["Deletion rate per base"]
        del star_qc_metric["Insertion average length"]
        del star_qc_metric["Insertion rate per base"]
        del star_qc_metric["Mismatch rate per base, %"]
        for key, value in star_qc_metric.items():
            star_qc_metric[key] = string_to_number(value)
        return self.queue_qc(
            star_qc_metric, encode_bam_file, "star-quality-metric", shared=True
        )  # backend mapping adding hyphens and removing caps

    def make_flagstat_qc(
        self,
        encode_file: EncodeFile,
        file: File,
        task_output_name: str,
        qc_dictionary_key: str,
    ) -> None:
        convert_to_string = ("mapped_pct", "paired_properly_pct", "singletons_pct")
        if encode_file.has_qc("SamtoolsFlagstatsQualityMetric"):
            return
        task = file.get_task()
        qc_file = self.analysis.search_up(task, "align", task_output_name)[0]
        qc = qc_file.read_json()
        output_qc = qc[qc_dictionary_key]
        for key in convert_to_string:
            # paired_properly_pct and singletons_pct are not there in single-ended
            try:
                output_qc[key] = str(output_qc[key])
            except KeyError:
                continue

        return self.queue_qc(
            output_qc, encode_file, "samtools-flagstats-quality-metric"
        )


class AccessionDnase(Accession):
    QC_MAP = {
        "unfiltered_flagstats": "make_unfiltered_flagstats_qc",
        "unfiltered_trimstats": "make_unfiltered_trimstats_qc",
        "nuclear_flagstats": "make_nuclear_flagstats_qc",
        "nuclear_duplication_metric": "make_nuclear_duplication_qc",
        "nuclear_hotspot1_metric": "make_nuclear_hotspot1_qc",
        "nuclear_samtools_stats": "make_nuclear_samtools_stats_qc",
        "unfiltered_samtools_stats": "make_unfiltered_samtools_stats_qc",
        "nuclear_alignment_quality_metric": "make_nuclear_alignment_qc",
        "footprints_quality_metric": "make_footprints_qc",
        "tenth_of_one_percent_peaks_qc": "make_tenth_of_one_percent_peaks_qc",
        "five_percent_allcalls_qc": "make_five_percent_allcalls_qc",
        "five_percent_narrowpeaks_qc": "make_five_percent_narrowpeaks_qc",
    }

    @property
    def assembly(self) -> str:
        filekey = "references.nuclear_chroms_gz"
        return self.find_portal_property_from_filekey(filekey, EncodeFile.ASSEMBLY)

    def preferred_default_should_be_updated(
        self, qc_value: Union[int, float], current_best_qc_value: Union[int, float]
    ) -> bool:
        return qc_value > current_best_qc_value

    def get_preferred_default_qc_value(self, file: File) -> Union[int, float]:
        """
        Find and parse the nuclear bam flagstats and get the number of "mapped" as int.
        """
        flagstats_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["nuclear_bam_qc"][
                "flagstats"
            ]
        )[0]
        flagstats_bytes = flagstats_file.read_bytes()
        flagstats = self.parse_dict_from_bytes(flagstats_bytes, parse_flagstats)
        return int(flagstats["mapped"])

    def parse_dict_from_bytes(
        self, qc_bytes: bytes, parser: Callable[[str], Dict[str, Any]]
    ) -> Dict[str, Any]:
        with impersonate_file(qc_bytes) as fake_file:
            result = parser(fake_file)
        return result

    def make_flagstats_qc(
        self, encode_file: EncodeFile, file: File, filekey: str
    ) -> None:
        """
        Filekey is either "nuclear_bam_qc" or "unfiltered_bam_qc"
        """
        if encode_file.has_qc("SamtoolsFlagstatsQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"][filekey]["flagstats"]
        )[
            0
        ]  # this is File
        qc_bytes = qc_file.read_bytes()
        with impersonate_file(qc_bytes) as flagstats:
            qc_output_dict = parse_flagstats(flagstats)
        qc_output_dict["mapped_pct"] = str(qc_output_dict["mapped_pct"])
        paired_properly_pct = qc_output_dict.get("paired_properly_pct")
        if paired_properly_pct is not None:
            qc_output_dict["paired_properly_pct"] = str(paired_properly_pct)
            qc_output_dict["singletons_pct"] = str(qc_output_dict["singletons_pct"])
        attachment = self.get_attachment(qc_file, "text/plain")
        qc_output_dict["attachment"] = attachment
        return self.queue_qc(
            qc_output_dict, encode_file, "samtools-flagstats-quality-metric"
        )

    def make_unfiltered_flagstats_qc(self, encode_file: EncodeFile, file: File) -> None:
        self.make_flagstats_qc(
            encode_file=encode_file, file=file, filekey="unfiltered_bam_qc"
        )

    def make_unfiltered_trimstats_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        If there is no trimstats qc then will return without queueing anything for
        posting.
        """
        qc_output_dict = {}
        if encode_file.has_qc("TrimmingQualityMetric"):
            return
        qc_files = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["unfiltered_bam_qc"][
                "trimstats"
            ]
        )
        if not qc_files:
            return
        attachment = self.get_attachment(qc_files[0], "text/plain")
        qc_output_dict["attachment"] = attachment
        return self.queue_qc(qc_output_dict, encode_file, "trimming-quality-metric")

    def make_nuclear_flagstats_qc(self, encode_file: EncodeFile, file: File) -> None:
        self.make_flagstats_qc(
            encode_file=encode_file, file=file, filekey="nuclear_bam_qc"
        )

    def make_nuclear_duplication_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        If data is SE then Picard MarkDuplicates library size estimate will be an empty
        string, need to handle.
        """
        if encode_file.has_qc("DuplicatesQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["nuclear_bam_qc"][
                "duplication_metrics"
            ]
        )[0]
        qc_bytes = qc_file.read_bytes()
        qc_output_dict = self.parse_dict_from_bytes(
            qc_bytes, parse_picard_duplication_metrics
        )
        if not qc_output_dict["Estimated Library Size"]:
            del qc_output_dict["Estimated Library Size"]
        attachment = self.get_attachment(
            qc_file, "text/plain", additional_extension=".txt"
        )
        qc_output_dict["attachment"] = attachment
        return self.queue_qc(qc_output_dict, encode_file, "duplicates-quality-metric")

    def make_nuclear_hotspot1_qc(self, encode_file: EncodeFile, file: File) -> None:
        if encode_file.has_qc("HotspotQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["nuclear_bam_qc"][
                "hotspot1"
            ]
        )[0]
        qc_bytes = qc_file.read_bytes()
        qc_output_dict = self.parse_dict_from_bytes(qc_bytes, parse_hotspot1_spot_score)
        attachment = self.get_attachment(
            qc_file, "text/plain", additional_extension=".txt"
        )
        qc_output_dict["attachment"] = attachment
        return self.queue_qc(qc_output_dict, encode_file, "hotspot-quality-metric")

    def make_samtools_stats_qc(
        self, encode_file: EncodeFile, file: File, filekey: str
    ) -> None:
        """
        Filekey is either unfiltered_bam_qc or nuclear_bam_qc.
        """
        if encode_file.has_qc("SamtoolsStatsQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"][filekey]["stats"]
        )[0]
        qc_bytes = qc_file.read_bytes()
        qc_output_dict = self.parse_dict_from_bytes(qc_bytes, parse_samtools_stats)
        attachment = self.get_attachment(qc_file, "text/plain")
        qc_output_dict["attachment"] = attachment
        non_encode_keys = [
            "total first fragment length",
            "total last fragment length",
            "average first fragment length",
            "average last fragment length",
            "maximum first fragment length",
            "maximum last fragment length",
            "percentage of properly paired reads (%)",
        ]
        for key in non_encode_keys:
            del qc_output_dict[key]
        return self.queue_qc(
            qc_output_dict, encode_file, "samtools-stats-quality-metric"
        )

    def make_nuclear_samtools_stats_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        self.make_samtools_stats_qc(
            encode_file=encode_file, file=file, filekey="nuclear_bam_qc"
        )

    def make_unfiltered_samtools_stats_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        self.make_samtools_stats_qc(
            encode_file=encode_file, file=file, filekey="unfiltered_bam_qc"
        )

    def make_nuclear_alignment_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        For SE data skip the insert size QC since it is only estimated for PE data.
        """
        if encode_file.has_qc("DnaseAlignmentQualityMetric"):
            return
        dnase_alignment_qc_output = {}

        insert_size_info_files = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["nuclear_bam_qc"][
                "insert_size_info"
            ]
        )
        if insert_size_info_files:
            insert_size_info_file = insert_size_info_files[0]
            insert_size_info_attachment = self.get_attachment(
                insert_size_info_file, "text/plain", additional_extension=".txt"
            )
            dnase_alignment_qc_output["attachment"] = insert_size_info_attachment
            insert_size_metric_file = self.analysis.get_files(
                filename=file.get_task().outputs["analysis"]["qc"]["nuclear_bam_qc"][
                    "insert_size_metrics"
                ]
            )[0]
            insert_size_metric_attachment = self.get_attachment(
                insert_size_metric_file, "text/plain", additional_extension=".txt"
            )
            dnase_alignment_qc_output[
                "insert_size_metric"
            ] = insert_size_metric_attachment

            insert_size_histogram_file = self.analysis.get_files(
                filename=file.get_task().outputs["analysis"]["qc"]["nuclear_bam_qc"][
                    "insert_size_histogram_pdf"
                ]
            )[0]
            insert_size_histogram_attachment = self.get_attachment(
                insert_size_histogram_file, "application/pdf"
            )
            dnase_alignment_qc_output[
                "insert_size_histogram"
            ] = insert_size_histogram_attachment

        nuclear_preseq_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["nuclear_bam_qc"][
                "preseq"
            ]
        )[0]
        nuclear_preseq_attachment = self.get_attachment(
            nuclear_preseq_file, "text/plain"
        )
        dnase_alignment_qc_output["nuclear_preseq"] = nuclear_preseq_attachment
        nuclear_preseq_targets_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["nuclear_bam_qc"][
                "preseq_targets"
            ]
        )[0]
        nuclear_preseq_targets_attachment = self.get_attachment(
            nuclear_preseq_targets_file, "text/plain"
        )
        dnase_alignment_qc_output[
            "nuclear_preseq_targets"
        ] = nuclear_preseq_targets_attachment

        return self.queue_qc(
            dnase_alignment_qc_output, encode_file, "dnase-alignment-quality-metric"
        )

    def make_footprints_qc(self, encode_file: EncodeFile, file: File) -> None:
        if encode_file.has_qc("DnaseFootprintingQualityMetric"):
            return
        footprint_count = int(
            file.get_task().outputs["analysis"]["qc"]["footprints_qc"][
                "one_percent_footprints_count"
            ]
        )
        dispersion_model_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["footprints_qc"][
                "dispersion_model"
            ]
        )[0]
        dispersion_model_attachment = self.get_attachment(
            dispersion_model_file, "application/json"
        )
        footprints_qc_output = {}  # type: Dict[str, Union[int, Dict[str,str]]]
        footprints_qc_output["footprint_count"] = footprint_count
        footprints_qc_output["dispersion_model"] = dispersion_model_attachment
        return self.queue_qc(
            footprints_qc_output, encode_file, "dnase-footprinting-quality-metric"
        )

    def make_tenth_of_one_percent_peaks_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        if encode_file.has_qc("HotspotsQualityMetric"):
            return
        tenth_of_percent_narrowpeaks_count = int(
            file.get_task().outputs["analysis"]["qc"]["peaks_qc"][
                "tenth_of_one_percent_narrowpeaks_count"
            ]
        )
        qc_output = {}
        qc_output[
            "tenth_of_one_percent_narrowpeaks_count"
        ] = tenth_of_percent_narrowpeaks_count
        return self.queue_qc(qc_output, encode_file, "hotspot-quality-metric")

    def make_five_percent_allcalls_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        if encode_file.has_qc("HotspotQualityMetric"):
            return
        five_percent_allcalls_count = int(
            file.get_task().outputs["analysis"]["qc"]["peaks_qc"][
                "five_percent_allcalls_count"
            ]
        )
        qc_output = {}
        qc_output["five_percent_allcalls_count"] = five_percent_allcalls_count
        return self.queue_qc(qc_output, encode_file, "hotspot-quality-metric")

    def make_five_percent_narrowpeaks_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        if encode_file.has_qc("HotspotQualityMetric"):
            return
        five_percent_narrowpeaks_count = int(
            file.get_task().outputs["analysis"]["qc"]["peaks_qc"][
                "five_percent_narrowpeaks_count"
            ]
        )
        five_percent_hotspots_count = int(
            file.get_task().outputs["analysis"]["qc"]["peaks_qc"][
                "five_percent_hotspots_count"
            ]
        )
        hotspot2_file = self.analysis.get_files(
            filename=file.get_task().outputs["analysis"]["qc"]["peaks_qc"]["hotspot2"]
        )[0]
        hotspot2_score = float(hotspot2_file.read_bytes().decode())
        qc_output = {}  # type: Dict[str, Union[int, float]]
        qc_output["five_percent_narrowpeaks_count"] = five_percent_narrowpeaks_count
        qc_output["five_percent_hotspots_count"] = five_percent_hotspots_count
        qc_output["spot2_score"] = hotspot2_score
        return self.queue_qc(qc_output, encode_file, "hotspot-quality-metric")


class AccessionLongReadRna(AccessionGenericRna):
    QC_MAP = {
        "long_read_rna_mapping": "make_long_read_rna_mapping_qc",
        "long_read_rna_quantification": "make_long_read_rna_quantification_qc",
        "long_read_rna_correlation": "make_long_read_rna_correlation_qc",
    }

    def _get_annotation_gtf(self) -> EncodeFile:
        """
        The name of the annotation file in the WDL task is not globally unique, so we
        cannot get it via `self.analysis.get_files` and instead need to go via the
        tasks.
        """
        gtf_filename = self.analysis.metadata.content["inputs"]["annotation"]
        gtf_file = self.analysis.get_files(filename=gtf_filename)[0]
        portal_gtf = self.get_encode_file_matching_md5_of_blob(gtf_file)
        if portal_gtf is None:
            raise ValueError(
                f"Could not find annotation GTF for file {gtf_file.filename}"
            )
        return portal_gtf

    @property
    def assembly(self) -> str:
        """
        Gets the assembly from the annotation GTF on the portal
        """
        annotation_gtf = self._get_annotation_gtf()
        assembly = annotation_gtf.get(EncodeFile.ASSEMBLY)
        if assembly is None:
            raise ValueError(
                f"Could not get assembly from annotation GTF {annotation_gtf.accession}"
            )
        return assembly

    @property
    def genome_annotation(self) -> str:
        """
        Gets the annotation version from the annotation GTF on the portal
        """
        annotation_gtf = self._get_annotation_gtf()
        genome_annotation = annotation_gtf.get(EncodeFile.GENOME_ANNOTATION)
        if genome_annotation is None:
            raise ValueError(
                f"Could not get genome annotation from annotation GTF {annotation_gtf.accession}"
            )
        return genome_annotation

    def get_preferred_default_qc_value(self, file: File) -> Union[float, int]:
        mapping_qc_file = self.analysis.search_up(
            file.get_task(), "minimap2", "mapping_qc"
        )[0].read_json()
        return int(mapping_qc_file["full_length_non_chimeric_reads"]["flnc"])

    def make_long_read_rna_correlation_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        """
        Make and post Spearman QC for long read RNA by giving the make_generic_correlation_qc the
        appropriate handler.
        """
        return self.make_generic_correlation_qc(
            encode_file, file, handler=self.prepare_long_read_rna_correlation_qc
        )

    def prepare_long_read_rna_correlation_qc(self, file: File) -> Dict[str, Any]:
        """
        Handler for creating the correlation QC object, specifically for long read rna. Finds and
        parses the spearman QC JSON.
        """
        task = file.get_task()
        qc_file = self.analysis.search_down(task, "calculate_spearman", "spearman")[0]
        qc = qc_file.read_json()
        spearman_value = qc["replicates_correlation"]["spearman_correlation"]
        spearman_correlation_qc = {"Spearman correlation": spearman_value}
        return spearman_correlation_qc

    def make_long_read_rna_mapping_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        """
        The commented lines add number_of_mapped_reads to the qc object, a field that is currently
        not valid under the schema.
        """
        if encode_file.has_qc("LongReadRnaMappingQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["mapping_qc"]
        )[0]
        qc = qc_file.read_json()
        output_qc: Dict[str, Any] = {}
        mr = "mapping_rate"
        flnc = qc["full_length_non_chimeric_reads"]["flnc"]
        output_qc["full_length_non_chimeric_read_count"] = int(flnc)
        output_qc[mr] = float(qc[mr][mr])
        return self.queue_qc(
            output_qc, encode_file, "long-read-rna-mapping-quality-metric"
        )

    def make_long_read_rna_quantification_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        if encode_file.has_qc("LongReadRnaQuantificationQualityMetric"):
            return
        ngd = "number_of_genes_detected"
        qc_file = self.analysis.get_files(filename=file.get_task().outputs[ngd])[0]
        qc = qc_file.read_json()
        output_qc = {"genes_detected": int(qc[ngd][ngd])}
        return self.queue_qc(
            output_qc, encode_file, "long-read-rna-quantification-quality-metric"
        )


class AccessionDnaseStarchFromBam(Accession):
    """
    See PROD-309. This is strictly meant for backfilling starch files into previously
    accessioned runs.
    """

    QC_MAP: Dict[str, str] = {}

    @property
    def assembly(self) -> str:
        filekey = "hotspot2_tar_gz"
        return self.find_portal_property_from_filekey(filekey, EncodeFile.ASSEMBLY)

    def preferred_default_should_be_updated(
        self, qc_value: Union[int, float], current_best_qc_value: Union[int, float]
    ) -> bool:
        """
        Dummy implementation since we don't have preferred_default specs for DNAse yet.
        """
        return super().preferred_default_should_be_updated(
            qc_value, current_best_qc_value
        )

    def get_preferred_default_qc_value(self, file: File) -> Union[int, float]:
        """
        Dummy implementation since we don't have preferred_default specs for dnase yet.
        """
        return super().get_preferred_default_qc_value(file)

    def post_analysis(self) -> EncodeGenericObject:
        """
        For these hacky runs we need to patch into the existing Analysis objects.
        """
        document_aliases = [
            f"{self.common_metadata.lab_pi}:cromwell-metadata-{self.analysis.workflow_id}"
        ]
        document_attachment = self.analysis.metadata.get_as_attachment(
            filename_prefix=self.experiment.accession
        )
        document = EncodeDocument(
            attachment=document_attachment,
            common_metadata=self.common_metadata,
            document_type=EncodeDocumentType.WorkflowMetadata,
            aliases=document_aliases,
        )
        posted_document = self.post_document(document)
        payload = {
            self.conn.PROFILE_KEY: "analysis",
            self.conn.ENCID_KEY: self.analysis.metadata.content["inputs"]["replicates"][
                0
            ]["analysis"],
            "files": [f.at_id for f in self.new_files],
            "documents": [posted_document.at_id],
        }

        response = self.conn.patch(payload, extend_array_values=True)
        modeled_analysis = EncodeGenericObject(response)
        return modeled_analysis

    def get_or_make_step_run(self, accession_step: AccessionStep) -> EncodeStepRun:
        """
        For the hacky runs we need to reuse the existing step runs.
        """
        return EncodeStepRun(
            self.conn.get(
                self.analysis.metadata.content["inputs"]["replicates"][0]["step_run"],
                frame="object",
            )
        )


class AccessionMicroRna(AccessionGenericRna):
    QC_MAP = {
        "mirna_mapping": "make_microrna_mapping_qc",
        "mirna_quantification": "make_microrna_quantification_qc",
        "mirna_correlation": "make_microrna_correlation_qc",
        "star": "make_star_qc_metric",
    }

    @property
    def assembly(self) -> str:
        filekey = "annotation"
        return self.find_portal_property_from_filekey(filekey, EncodeFile.ASSEMBLY)

    @property
    def genome_annotation(self) -> str:
        filekey = "annotation"
        return self.find_portal_property_from_filekey(
            filekey, EncodeFile.GENOME_ANNOTATION
        )

    def get_preferred_default_qc_value(self, file: File) -> Union[float, int]:
        mapping_qc_file = self.analysis.search_up(
            file.get_task(), "star", "star_qc_json"
        )[0].read_json()
        return int(mapping_qc_file["aligned_reads"]["aligned_reads"])

    def make_microrna_quantification_qc(
        self, encode_file: EncodeFile, file: File
    ) -> None:
        if encode_file.has_qc("MicroRnaQuantificationQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["star_qc_json"]
        )[0]
        qc = qc_file.read_json()
        expressed_mirnas_qc = qc["expressed_mirnas"]
        return self.queue_qc(
            expressed_mirnas_qc, encode_file, "micro-rna-quantification-quality-metric"
        )

    def make_microrna_mapping_qc(self, encode_file: EncodeFile, file: File) -> None:
        if encode_file.has_qc("MicroRnaMappingQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["star_qc_json"]
        )[0]
        qc = qc_file.read_json()
        aligned_reads_qc = qc["aligned_reads"]
        return self.queue_qc(
            aligned_reads_qc, encode_file, "micro-rna-mapping-quality-metric"
        )

    def make_microrna_correlation_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        Returns without queueing this QC for posting if the experiment is not replicated, since
        correlation is computed between pairs of replicates.
        """
        if (
            encode_file.has_qc("CorrelationQualityMetric")
            or self.experiment.get_number_of_biological_replicates() != 2
        ):
            return
        task = file.get_task()
        qc_file = self.analysis.search_down(
            task, "spearman_correlation", "spearman_json"
        )[0]
        qc = qc_file.read_json()
        spearman_value = qc["spearman_correlation"]["spearman_correlation"]
        spearman_correlation_qc = {"Spearman correlation": spearman_value}
        return self.queue_qc(
            spearman_correlation_qc,
            encode_file,
            "correlation-quality-metric",
            shared=True,
        )

    def make_star_qc_metric(self, encode_bam_file: EncodeFile, file: File) -> None:
        if encode_bam_file.has_qc("StarQualityMetric"):
            return
        qc_file = self.analysis.get_files(
            filename=file.get_task().outputs["star_qc_json"]
        )[0]
        qc = qc_file.read_json()
        star_qc_metric = qc["star_qc_metric"]
        del star_qc_metric["Started job on"]
        del star_qc_metric["Started mapping on"]
        del star_qc_metric["Finished on"]
        for key, value in star_qc_metric.items():
            star_qc_metric[key] = string_to_number(value)
        return self.queue_qc(star_qc_metric, encode_bam_file, "star-quality-metric")


class AccessionAtacChip(Accession):
    """
    Hold methods shared between ChIP and ATAC accessioning, since the pipelines are very
    similar. In theory this should somehow be an abstract class, but multiple
    inheritance with ABC is tricky, and overkill to implement here.
    """

    @property
    def assembly(self) -> str:
        filekey = "ref_fa"
        try:
            files = self.analysis.get_files(filekey)
            if not files:
                raise ValueError(f"Could not find any files matching filekey {filekey}")
            portal_index = self.get_encode_file_matching_md5_of_blob(files[0])
            if portal_index is None:
                raise ValueError("Could not find portal index")
            portal_assembly = portal_index.get(EncodeFile.ASSEMBLY)
            if portal_assembly is None:
                raise ValueError(
                    f"Could not find assembly for portal file {portal_index.at_id}"
                )
        except ValueError:
            self.logger.exception("Could not determine assembly")
            raise
        return portal_assembly

    @property
    def pipeline_version(self) -> str:
        """
        Need to override implementation in base class since ChIP and ATAC don't have
        `workflow.meta.version` in WDL.
        """
        qc = self.analysis.get_files("qc_json")[0].read_json()
        version = qc["general"]["pipeline_ver"].lstrip("v")
        return version

    def preferred_default_should_be_updated(
        self, qc_value: Union[int, float], current_best_qc_value: Union[int, float]
    ) -> bool:
        """
        Dummy implementation since ATAC/ChIP have their own mechanism to compute
        preferred_defaults.
        """
        return super().preferred_default_should_be_updated(
            qc_value, current_best_qc_value
        )

    def get_preferred_default_qc_value(self, file: File) -> Union[int, float]:
        """
        Dummy implementation since ATAC/ChIP have their own mechanism to compute
        preferred_defaults.
        """
        return super().get_preferred_default_qc_value(file)

    def get_atac_chip_pipeline_replicate(self, file: File) -> str:
        """
        Searches for the input fastq array corresponding to the ancestor input fastqs of the current
        file and returns the pipeline replicate number. We only need to check R1, since it will
        always be there in both the single and paired ended runs of the ChIP pipeline. We need this
        in order to be able to identify the correct QC in the QC JSON.
        """
        task = file.get_task()
        upstream_task_name = "align"
        if task.task_name.endswith("ctl"):
            upstream_task_name += "_ctl"
        parent_fastqs = [
            file.filename
            for file in self.analysis.search_up(
                task, upstream_task_name, "fastqs_R1", inputs=True
            )
        ]
        pipeline_rep = None
        for k, v in self.analysis.metadata.content["inputs"].items():
            if "fastqs" in k:
                if sorted(v) == sorted(parent_fastqs):
                    if "ctl" in k:
                        pipeline_rep = "ctl" + k.split("_")[2].lstrip("rep")
                    else:
                        pipeline_rep = k.split("_")[1]
                    break
        if not pipeline_rep:
            raise ValueError(
                "Could not determine pipeline replicate number for file {}".format(file)
            )
        return pipeline_rep

    def get_number_of_replicates(self) -> int:
        """
        Obtains the number of replicates used in running the pipeline.
        """
        num_reps = 0
        for k, v in self.analysis.metadata.content["inputs"].items():
            if k.startswith("fastqs_rep") and k.endswith("R1") and len(v) > 0:
                num_reps += 1
        return num_reps

    def add_mapped_read_length(self, file: File) -> Dict[str, int]:
        """
        Obtains the value of mapped_read_length to post for bam files from the read
        length log in the ancestor align task in the ChIP-seq pipeline.
        """
        task = file.get_task()
        upstream_task_name = "align"
        if task.task_name.endswith("ctl"):
            upstream_task_name += "_ctl"
        read_len_log = self.analysis.search_up(
            task, upstream_task_name, "read_len_log"
        )[0]
        log_contents = read_len_log.read_bytes()
        try:
            mapped_read_length = int(log_contents)
        except ValueError as e:
            raise RuntimeError(
                f"Could not parse read length log into integer: tried to parse {str(log_contents)}"
            ) from e
        return {"mapped_read_length": mapped_read_length}

    def add_mapped_run_type(self, file: File) -> Dict[str, str]:
        """
        Obtains the value of `mapped_run_type` to post for bam files from the read
        length log in the ancestor align task in the ChIP-seq pipeline, useful for
        detecting PE data that was mapped as SE on the portal.
        """
        replicate = self.get_atac_chip_pipeline_replicate(file)
        qc = self.analysis.get_files("qc_json")[0].read_json()
        is_paired_end = qc["general"]["seq_endedness"][replicate]["paired_end"]
        if not isinstance(is_paired_end, bool):
            raise TypeError(
                f"Expected boolean for ChIP QC value general.seq_endedness.{replicate}.paired_end, found {is_paired_end}"
            )
        mapped_run_type = "paired-ended" if is_paired_end else "single-ended"
        return {"mapped_run_type": mapped_run_type}

    def maybe_conservative_set(self, file: File) -> Dict[str, str]:
        """
        For replicated ChIP/ATAC experiments, the exact file that is to be labeled as
        the conservative set may vary. As such, this callback is registered for any
        file that might need to have this value set in the steps JSON, and called at
        file object generation time (make_file_obj) to fill in (or not) the missing
        value.
        """
        qc = self.analysis.get_files("qc_json")[0].read_json()["replication"][
            "reproducibility"
        ]["idr"]

        consv_set = qc["consv_set"]
        current_set = file.get_task().inputs["prefix"]
        if current_set == consv_set:
            return {"output_type": "conservative IDR thresholded peaks"}
        return {}

    def maybe_preferred_default_bigwig(self, file: File) -> Dict[str, bool]:
        task_name = file.get_task().task_name
        if self.get_number_of_replicates() == 1 and task_name == "macs2_signal_track":
            return {"preferred_default": True}
        elif task_name == "macs2_signal_track_pooled":
            return {"preferred_default": True}
        else:
            return {}


class AccessionChip(AccessionAtacChip):
    QC_MAP = {
        "chip_alignment": "make_chip_alignment_qc",
        "chip_align_enrich": "make_chip_align_enrich_qc",
        "chip_library": "make_chip_library_qc",
        "chip_replication": "make_chip_replication_qc",
        "chip_peak_enrichment": "make_chip_peak_enrichment_qc",
    }

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

    def maybe_preferred_default(self, file: File) -> Dict[str, bool]:
        """
        For replicated ChIP-seq experiment, the exact file that is to be labeled with
        preferred_default=true may vary. As such, this callback is registered for any
        file that might need to have this value set in the steps JSON, and called at
        file object generation time (make_file_obj) to fill in (or not) the missing
        value.
        """
        qc = self.analysis.get_files("qc_json")[0].read_json()
        method = self.get_chip_pipeline_replication_method(qc)
        if self.get_number_of_replicates() == 1:
            if (
                file.get_task().task_name
                == f"{self.get_chip_pipeline_replication_method(qc)}_pr"
            ):
                return {"preferred_default": True}
            return {}
        replication_qc = qc["replication"]["reproducibility"][method]

        optimal_set = replication_qc["opt_set"]
        current_set = file.get_task().inputs["prefix"]
        if current_set == optimal_set:
            return {"preferred_default": True}
        return {}

    def maybe_add_cropped_read_length(self, file: File) -> Dict[str, int]:
        """
        Obtains the value of mapped_read_length to post for bam files from the
        crop_length input of the ancestor align task in the ChIP-seq pipeline. If the
        crop_length in the pipeline is 0, then no cropping was performed and the
        cropped_read_length will not be posted (return empty dict).

        Note that here we are assuming the crop length will always be the same for all
        of the align tasks
        """
        align_task = self.analysis.get_tasks(task_name="align")[0]
        crop_length = align_task.inputs["crop_length"]
        if crop_length == 0:
            return {}
        return {"cropped_read_length": crop_length}

    def maybe_add_cropped_read_length_tolerance(self, file: File) -> Dict[str, int]:
        """
        Obtains the value of cropped_read_length_tolerance to post for bam files from
        crop_length input of an arbitrary align task in the pipeline (value will be the
        same for all align tasks since the tolerance is a global parameter). If the
        crop_length in the pipeline is 0, then no cropping was performed and the
        cropped_read_length_tolerance will not be posted (return empty dict).

        Note that here we are assuming the crop length will always be the same for all
        of the align tasks
        """
        align_task = self.analysis.get_tasks(task_name="align")[0]
        crop_length = align_task.inputs["crop_length"]
        crop_length_tol = align_task.inputs.get("crop_length_tol")
        if crop_length == 0 or crop_length_tol is None:
            return {}
        return {"cropped_read_length_tolerance": crop_length_tol}

    def make_chip_alignment_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        This function typecasts to match the ENCODE schema. Trucated zero values could
        potentially be deserialized from the qc json as integers instead of floats.
        """
        if encode_file.has_qc("ChipAlignmentQualityMetric"):
            return
        qc = self.analysis.get_files("qc_json")[0].read_json()
        replicate = self.get_atac_chip_pipeline_replicate(file)
        if "unfiltered" in encode_file.output_type:
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

    def make_chip_align_enrich_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        The xcor plots are not downstream of encode_file, in fact, they don't even share
        a common parent task with encode_file. Instead, we search up to find the parent
        align task of the current filtered bam, find the corresponding align_R1 task
        with the same fastq input, and search downstream from there for the xcor plot.
        """
        if encode_file.has_qc("ChipAlignmentEnrichmentQualityMetric"):
            return
        task = file.get_task()
        qc = self.analysis.get_files("qc_json")[0].read_json()
        replicate = self.get_atac_chip_pipeline_replicate(file)
        upstream_task_name = "align"
        if replicate.startswith("ctl"):
            upstream_task_name += "ctl"
        key_to_match = "fastqs_R1"
        parent_fastqs = [
            file.filename
            for file in self.analysis.search_up(
                task, upstream_task_name, key_to_match, inputs=True
            )
        ]
        align_r1_tasks = self.analysis.get_tasks("align_R1")
        start_task = [
            i
            for i in align_r1_tasks
            if sorted(i.inputs[key_to_match]) == sorted(parent_fastqs)
        ]
        if len(start_task) != 1:
            try:
                raise ValueError(
                    (
                        f"Incorrect number of candidate start tasks with {key_to_match}: "
                        f"expected 1 but found {len(start_task)}"
                    )
                )
            except ValueError:
                self.logger.exception(
                    "Could not make ChipAlignEnrichQualityMetric for file %s",
                    file.filename,
                )
                raise
        cross_corr_plot_pdf = self.analysis.search_down(
            start_task[0], "xcor", "plot_pdf"
        )[0]
        fingerprint_plot_png = self.analysis.search_down(task, "jsd", "plot")[0]
        gc_bias_plot_png = self.analysis.search_down(task, "gc_bias", "gc_plot")[0]
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

    def make_chip_library_qc(self, encode_file: EncodeFile, file: File) -> None:
        if encode_file.has_qc("ChipLibraryQualityMetric"):
            return
        qc = self.analysis.get_files("qc_json")[0].read_json()
        replicate = self.get_atac_chip_pipeline_replicate(file)
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

    def make_chip_replication_qc(self, encode_file: EncodeFile, file: File) -> None:
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
        if encode_file.has_qc("ChipReplicationQualityMetric"):
            return
        raw_qc = self.analysis.get_files("qc_json")[0].read_json()
        method = self.get_chip_pipeline_replication_method(raw_qc)
        qc = raw_qc["replication"]["reproducibility"][method]

        optimal_set = qc["opt_set"]
        task = file.get_task()
        current_set = task.inputs["prefix"]
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

        task_name = task.task_name
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
            output_qc["idr_cutoff"] = float(task.inputs["idr_thresh"])
            idr_plot_png = self.analysis.get_files(filename=task.outputs["idr_plot"])[0]
            idr_log = self.analysis.get_files(filename=task.outputs["idr_log"])[0]
            output_qc.update(
                {"idr_dispersion_plot": self.get_attachment(idr_plot_png, "image/png")}
            )
            output_qc.update(
                {
                    "idr_parameters": self.get_attachment(
                        idr_log, "text/plain", additional_extension=".txt"
                    )
                }
            )
        return self.queue_qc(output_qc, encode_file, "chip-replication-quality-metric")

    def make_chip_peak_enrichment_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        The peak region stats are only useful for the optimal set, since the ones for
        rep1 and rep2 are applicable to files that are not posted by to the portal.
        IDR frip scores are applicable to any pair undergoing IDR, so they are always
        looked for.
        """
        if encode_file.has_qc("ChipPeakEnrichmentQualityMetric"):
            return

        qc = self.analysis.get_files("qc_json")[0].read_json()
        method = self.get_chip_pipeline_replication_method(qc)

        optimal_set = qc["replication"]["reproducibility"][method]["opt_set"]
        current_set = file.get_task().inputs["prefix"]

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


class AccessionAtac(AccessionAtacChip):
    QC_MAP = {
        "atac_alignment": "make_atac_alignment_qc",
        "atac_align_enrich": "make_atac_align_enrich_qc",
        "atac_library": "make_atac_library_qc",
        "atac_replication": "make_atac_replication_qc",
        "atac_peak_enrichment": "make_atac_peak_enrichment_qc",
    }

    def maybe_preferred_default(self, file: File) -> Dict[str, bool]:
        """
        For ATAC one of the replicated/PPR overlap peak sets is labeled as
        `preferred_default`.
        """
        if self.get_number_of_replicates() == 1:
            if file.get_task().task_name == "overlap_pr":
                return {"preferred_default": True}
            return {}
        qc = self.analysis.get_files("qc_json")[0].read_json()
        replication_qc = qc["replication"]["reproducibility"]["overlap"]

        optimal_set = replication_qc["opt_set"]
        current_set = file.get_task().inputs["prefix"]
        if current_set == optimal_set:
            return {"preferred_default": True}
        return {}

    def make_atac_alignment_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        Constructs postable QC from the `samstat` and `nodup_samstat` sections of the
        ATAC global QC for the raw and filtered bams, respectively, and also adds in
        `frac_mito` and `frag_len_stat` for both the bams.
        """
        if encode_file.has_qc("AtacAlignmentQualityMetric"):
            return
        qc = self.analysis.get_files("qc_json")[0].read_json()
        replicate = self.get_atac_chip_pipeline_replicate(file)
        if "unfiltered" in encode_file.output_type:
            qc_key, processing_stage = "samstat", "unfiltered"
        else:
            qc_key, processing_stage = "nodup_samstat", "filtered"
        output_qc = {}
        output_qc["processing_stage"] = processing_stage
        output_qc.update(qc["align"][qc_key][replicate])
        output_qc.update(qc["align"]["frac_mito"][replicate])
        if file.get_task().inputs["paired_end"] is True:
            output_qc.update(qc["align"]["frag_len_stat"][replicate])
        return self.queue_qc(output_qc, encode_file, "atac-alignment-quality-metric")

    def make_atac_align_enrich_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        Similar to ChIP, except no xcor is needed and ATAC has TSS enrichment.
        """
        if encode_file.has_qc("AtacAlignmentEnrichmentQualityMetric"):
            return
        task = file.get_task()
        qc = self.analysis.get_files("qc_json")[0].read_json()
        replicate = self.get_atac_chip_pipeline_replicate(file)
        fingerprint_plot_png = self.analysis.search_down(task, "jsd", "plot")[0]
        gc_bias_plot_png = self.analysis.search_down(task, "gc_bias", "gc_plot")[0]
        tss_enrichment_plot_png = self.analysis.search_down(
            task, "tss_enrich", "tss_large_plot"
        )[0]
        output_qc = {}
        output_qc.update(qc["align_enrich"]["jsd"][replicate])
        output_qc.update(qc["align"]["frac_reads_in_annot"][replicate])
        output_qc.update(
            {
                "tss_enrichment": qc["align_enrich"]["tss_enrich"][replicate][
                    "tss_enrich"
                ]
            }
        )
        output_qc.update(
            {
                "jsd_plot": self.get_attachment(fingerprint_plot_png, "image/png"),
                "gc_bias_plot": self.get_attachment(gc_bias_plot_png, "image/png"),
                "tss_enrichment_plot": self.get_attachment(
                    tss_enrichment_plot_png, "image/png"
                ),
            }
        )
        fri_blacklist = output_qc.pop("fri_blacklist", None)
        if fri_blacklist is not None:
            output_qc["fri_exclusion_list"] = fri_blacklist
        return self.queue_qc(
            output_qc, encode_file, "atac-alignment-enrichment-quality-metric"
        )

    def make_atac_library_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        The ATAC pipeline only produces fragment length distribution plots for paired
        end data, so we need to check the bam endedness before searching the analysis
        for the plot.
        """
        if encode_file.has_qc("AtacLibraryQualityMetric"):
            return
        task = file.get_task()
        qc = self.analysis.get_files("qc_json")[0].read_json()
        replicate = self.get_atac_chip_pipeline_replicate(file)
        output_qc = {
            **qc["align"]["dup"][replicate],
            **qc["lib_complexity"]["lib_complexity"][replicate],
        }
        if file.get_task().inputs["paired_end"] is True:
            fragment_length_plot_png = self.analysis.search_down(
                task, "fraglen_stat_pe", "fraglen_dist_plot"
            )[0]
            output_qc["fragment_length_distribution_plot"] = self.get_attachment(
                fragment_length_plot_png, "image/png"
            )
        return self.queue_qc(
            output_qc, encode_file, "atac-library-complexity-quality-metric"
        )

    def make_atac_replication_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        Rescue ratio and self-consistency ratio are only reported for optimal set. This
        set is determined by checking the QC JSON, and comparing to the prefix in the
        IDR task input in the WDL.

        The value of the QC's `reproducible_peaks` depends on the replicates or
        psuedo-replicates being compared.

        IDR cutoff, plot, and log are always reported for all IDR thresholded peaks
        files. They are not reported for the files using overlap. The IDR log file
        attachment is fudged with a .txt extension so that the portal can guess the mime
        type correctly and accept the file as valid.
        """
        if encode_file.has_qc("AtacReplicationQualityMetric"):
            return

        raw_qc = self.analysis.get_files("qc_json")[0].read_json()
        task = file.get_task()
        task_name = task.task_name
        method = task_name.split("_")[0]
        qc = raw_qc["replication"]["reproducibility"][method]

        optimal_set = qc["opt_set"]
        current_set = task.inputs["prefix"]
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
            output_qc["idr_cutoff"] = float(task.inputs["idr_thresh"])
            idr_plot_png = self.analysis.get_files(filename=task.outputs["idr_plot"])[0]
            idr_log = self.analysis.get_files(filename=task.outputs["idr_log"])[0]
            output_qc.update(
                {"idr_dispersion_plot": self.get_attachment(idr_plot_png, "image/png")}
            )
            output_qc.update(
                {
                    "idr_parameters": self.get_attachment(
                        idr_log, "text/plain", additional_extension=".txt"
                    )
                }
            )
        return self.queue_qc(output_qc, encode_file, "atac-replication-quality-metric")

    def make_atac_peak_enrichment_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        The peak region stats are only useful for the optimal set, since the ones for
        rep1 and rep2 are applicable to files that are not posted by to the portal.
        IDR frip scores are applicable to any pair undergoing IDR, so they are always
        looked for.
        """
        if encode_file.has_qc("AtacPeakEnrichmentQualityMetric"):
            return

        qc = self.analysis.get_files("qc_json")[0].read_json()
        task = file.get_task()
        method = task.task_name.split("_")[0]

        optimal_set = qc["replication"]["reproducibility"][method]["opt_set"]
        current_set = task.inputs["prefix"]

        output_qc = {
            "frip": qc["peak_enrich"]["frac_reads_in_peaks"][method][current_set][
                "frip"
            ]
        }
        if current_set == optimal_set:
            output_qc.update(qc["peak_stat"]["peak_region_size"][f"{method}_opt"])
        for k, v in output_qc.items():
            if k in ["mean", "frip"]:
                output_qc[k] = float(v)
            else:
                output_qc[k] = int(v)
        return self.queue_qc(
            output_qc, encode_file, "atac-peak-enrichment-quality-metric"
        )


class AccessionWgbs(Accession):
    QC_MAP = {
        "gembs_alignment": "make_gembs_alignment_qc",
        "samtools_stats": "make_samtools_stats_qc",
        "cpg_correlation": "make_cpg_correlation_qc",
    }

    @property
    def assembly(self) -> str:
        filekey = "reference"
        return self.find_portal_property_from_filekey(filekey, EncodeFile.ASSEMBLY)

    @property
    def experiment(self) -> EncodeExperiment:
        """
        We override the implementation in the base class because in the WGBS pipeline
        both the `make_metadata_csv` and `map` tasks have `fastqs` as input, but in one
        of them it is a JSON file containing file paths and not the actual fastqs,
        which is not present on the portal. So we need to manually dig up one of the
        fastqs to find on the portal.
        """
        if self._experiment is None:
            map_task = self.analysis.get_tasks("map")[0]
            fastq_filename = map_task.inputs["fastqs"][0]
            encode_file = self.get_encode_file_matching_md5_of_blob(
                self.analysis.get_files(filename=fastq_filename)[0]
            )
            if encode_file is None:
                raise ValueError("Could not find raw fastqs on the portal")
            experiment_obj = self.conn.get(encode_file.dataset, frame="embedded")
            self._experiment = EncodeExperiment(experiment_obj)
        return self._experiment

    def preferred_default_should_be_updated(
        self, qc_value: Union[int, float], current_best_qc_value: Union[int, float]
    ) -> bool:
        return qc_value > current_best_qc_value

    def get_preferred_default_qc_value(self, file: File) -> Union[int, float]:
        bam_file = self.analysis.search_up(file.get_task(), "map", "bam")[0]
        gembs_map_qc = self.analysis.search_down(
            bam_file.get_task(), "qc_report", "portal_map_qc_json"
        )[0].read_json()
        return gembs_map_qc["general_reads"]

    def make_gembs_alignment_qc(self, encode_file: EncodeFile, file: File) -> None:
        """
        Several of the properties in the QC are useless so we don't post the to the
        portal. Furthermore the pipeline QC use values between 0 and 1 for percentages
        but the portal usually uses values between 0 and 100 so we make sure to multiply
        any percentages by 100.
        """
        if encode_file.has_qc("GembsAlignmentQualityMetric"):
            return
        task = file.get_task()
        output_qc = {}
        gembs_qc_file = self.analysis.search_down(
            task, "qc_report", "portal_map_qc_json"
        )[0]
        gembs_qc = gembs_qc_file.read_json()
        output_qc.update(
            {
                k: v
                for k, v in gembs_qc.items()
                if k
                not in (
                    "pct_reads_in_control_sequences",
                    "pct_sequenced_reads",
                    "reads_in_control_sequences",
                )
            }
        )
        mapq_plot_png = self.analysis.search_down(
            task, "qc_report", "map_qc_mapq_plot_png"
        )[0]
        output_qc["mapq_plot"] = self.get_attachment(
            mapq_plot_png, mime_type="image/png"
        )
        insert_size_plot_png = self.analysis.search_down(
            task, "qc_report", "map_qc_insert_size_plot_png"
        )
        if insert_size_plot_png:
            output_qc["insert_size_plot"] = self.get_attachment(
                insert_size_plot_png[0], mime_type="image/png"
            )
        average_coverage_qc_file = self.analysis.search_down(
            task, "calculate_average_coverage", "average_coverage_qc"
        )[0]
        average_coverage_qc = average_coverage_qc_file.read_json()
        output_qc.update(average_coverage_qc["average_coverage"])
        for k, v in output_qc.items():
            if k.startswith("pct"):
                output_qc[k] = 100 * v
        return self.queue_qc(output_qc, encode_file, "gembs-alignment-quality-metric")

    def make_samtools_stats_qc(self, encode_file: EncodeFile, file: File) -> None:
        if encode_file.has_qc("SamtoolsStatsQualityMetric"):
            return
        task = file.get_task()
        output_qc = {}
        samtools_stats_qc_file = self.analysis.search_down(
            task, "calculate_average_coverage", "average_coverage_qc"
        )[0]
        samtools_stats_qc = samtools_stats_qc_file.read_json()
        output_qc.update(
            {
                k: v
                for k, v in samtools_stats_qc["samtools_stats"].items()
                if k
                not in [
                    "total first fragment length",
                    "total last fragment length",
                    "average first fragment length",
                    "average last fragment length",
                    "maximum first fragment length",
                    "maximum last fragment length",
                    "percentage of properly paired reads (%)",
                ]
            }
        )
        return self.queue_qc(output_qc, encode_file, "samtools-stats-quality-metric")

    def make_cpg_correlation_qc(self, encode_file: EncodeFile, file: File) -> None:
        if (
            encode_file.has_qc("CpgCorrelationQualityMetric")
            or len(self.analysis.metadata.content["inputs"]["wgbs.fastqs"]) != 2
        ):
            return

        task = file.get_task()
        output_qc = {}
        cpg_correlation_qc_file = self.analysis.search_down(
            task, "calculate_bed_pearson_correlation", "bed_pearson_correlation_qc"
        )[0]
        cpg_correlation_qc = cpg_correlation_qc_file.read_json()
        output_qc["Pearson correlation"] = cpg_correlation_qc["pearson_correlation"][
            "pearson_correlation"
        ]
        return self.queue_qc(
            output_qc, encode_file, "cpg-correlation-quality-metric", shared=True
        )


class AccessionHic(Accession):
    QC_MAP = {"hic": "make_hic_qc"}

    @property
    def assembly(self) -> str:
        filekey = "reference_index"
        return self.find_portal_property_from_filekey(filekey, EncodeFile.ASSEMBLY)

    def get_preferred_default_qc_value(self, file: File) -> Union[int, float]:
        raise NotImplementedError

    def preferred_default_should_be_updated(
        self, qc_value: Union[int, float], current_best_qc_value: Union[int, float]
    ) -> bool:
        raise NotImplementedError

    def maybe_preferred_default(self, file: File) -> Dict[str, bool]:
        """
        Needed for the .hic files. For in-situ Hi-C MAPQ>=30 should be the default and
        for intact Hi-C it should be the MAPQ>=1 map. However there is no reliable way
        to distinguish this in the portal metadata so we just use the MAPQ>=30 for now.
        """
        task = file.get_task()
        preferred_default_payload = {"preferred_default": True}
        if task.task_name == "create_eigenvector":
            if task.inputs["output_filename_suffix"] == "_30":
                return preferred_default_payload
        elif task.inputs["quality"] == 30:
            return preferred_default_payload
        return {}

    def maybe_update_output_type(self, file: File) -> Dict[str, str]:
        quality = file.get_task().inputs["quality"]
        if quality == 30:
            return {"output_type": "mapping quality thresholded chromatin interactions"}
        return {}

    def add_filter_value(self, file: File) -> Dict[str, str]:
        return {"filter_value": file.get_task().inputs["quality"]}

    def make_hic_qc(self, encode_file: EncodeFile, file: File) -> None:
        if encode_file.has_qc("HicQualityMetric"):
            return
        task = file.get_task()
        if task.task_name == "dedup":
            hic_qc_file = self.analysis.search_down(
                task, "calculate_stats_on_library", "stats_json"
            )[0]
            hic_qc_text = self.analysis.search_down(
                task, "calculate_stats_on_library", "stats"
            )[0]
        else:
            hic_qc_file = self.analysis.search_up(
                task, "calculate_stats", "stats_json"
            )[0]
            hic_qc_text = self.analysis.search_up(task, "calculate_stats", "stats")[0]
        hic_qc = hic_qc_file.read_json()
        modeled_attachment = EncodeAttachment(
            hic_qc_text.read_bytes(), hic_qc_text.filename, mime_type="text/plain"
        )
        attachment = modeled_attachment.get_portal_object()
        hic_qc["attachment"] = attachment
        return self.queue_qc(hic_qc, encode_file, "hic-quality-metric")


def accession_factory(
    pipeline_type: str,
    accession_metadata: str,
    server: str,
    lab: str,
    award: str,
    backend: Optional[Backend] = None,
    no_log_file: bool = False,
    log_file_path: str = "accession.log",
    queue_info: Optional[QueueInfo] = None,
    use_in_memory_db: bool = False,
) -> Accession:
    """
    Matches against the user-specified pipeline_type string and returns an instance of
    the appropriate accession subclass. Usage of this factory has the nice effect of
    automatically supplying the appropriate AccessionSteps based on the pipeline name.
    """
    pipeline_type_map = {
        "bulk_rna": AccessionBulkRna,
        "bulk_rna_no_kallisto": AccessionBulkRna,
        "bulk_rna_pbam": AccessionBulkRnaPbam,
        "mirna": AccessionMicroRna,
        "long_read_rna": AccessionLongReadRna,
        "chip_map_only": AccessionChip,
        "tf_chip_peak_call_only": AccessionChip,
        "tf_chip_bwa_control_fastqs": AccessionChip,
        "histone_chip_peak_call_only": AccessionChip,
        "mint_chip_peak_call_only": AccessionChip,
        "tf_chip": AccessionChip,
        "histone_chip": AccessionChip,
        "mint_chip": AccessionChip,
        "control_chip": AccessionChip,
        "atac": AccessionAtac,
        "dnase": AccessionDnase,
        "dnase_no_footprints": AccessionDnase,
        "dnase_starch_from_bam": AccessionDnaseStarchFromBam,
        "wgbs": AccessionWgbs,
        "hic": AccessionHic,
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

    metadata = metadata_factory(accession_metadata)
    if pipeline_type == "long_read_rna":
        pipeline_type = _get_long_read_rna_steps_json_name_prefix_from_metadata(
            metadata
        )

    private_filenames = False
    if pipeline_type in ("control_chip", "tf_chip", "histone_chip"):
        if _chip_pbam_used(metadata):
            pipeline_type = pipeline_type + "_pbam"
            private_filenames = True

    if pipeline_type == "bulk_rna_pbam":
        private_filenames = True

    steps_json_path = (
        current_dir.parents[1] / "accession_steps" / f"{pipeline_type}_steps.json"
    )
    accession_steps = AccessionSteps(steps_json_path)
    if backend is None:
        backend = backend_factory(metadata.backend_name)
    if isinstance(backend, LocalBackend) and queue_info is not None:
        raise ValueError("Cannot use Cloud Tasks queue with local backend.")
    analysis = Analysis(
        metadata,
        raw_fastqs_keys=accession_steps.raw_fastqs_keys,
        raw_fastqs_can_have_task=accession_steps.raw_fastqs_can_have_task,
        backend=backend,
    )
    connection = Connection(server, no_log_file=True)
    common_metadata = EncodeCommonMetadata(lab, award)
    recorder = Recorder(use_in_memory_db=use_in_memory_db)
    return selected_accession(
        accession_steps,
        analysis,
        connection,
        common_metadata,
        log_file_path=log_file_path,
        no_log_file=no_log_file,
        queue_info=queue_info,
        private_filenames=private_filenames,
        recorder=recorder,
    )


def _get_long_read_rna_steps_json_name_prefix_from_metadata(metadata: Metadata) -> str:
    """
    The JSON template to use for long read RNA depends on the number of spikeins, this
    function determines the appropriate one to use from the metadata.
    """
    num_spikeins = len(metadata.content["inputs"]["spikeins"])
    if num_spikeins == 0:
        return "long_read_rna_no_spikeins"
    if num_spikeins == 1:
        return "long_read_rna_one_spikein"
    return "long_read_rna_two_or_more_spikeins"


def _chip_pbam_used(metadata: Metadata) -> bool:
    """
    If data was processed using pbam conversion via `redact_nodup_bam: true` in pipeline
    input then need to select the pbam template.
    """
    return metadata.content["inputs"].get("redact_nodup_bam", False)
