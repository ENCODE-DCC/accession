import json
import logging
from hashlib import md5
from typing import Dict, Optional

import attr
import google.auth
from google.api_core.exceptions import GoogleAPICallError, RetryError
from google.cloud import tasks_v2
from typing_extensions import TypedDict

from accession.backends import GcsBlob
from accession.logger_factory import logger_factory

APP_ENGINE_UPLOAD_ENDPOINT = "/upload"

AppEngineHttpRequest = TypedDict(
    "AppEngineHttpRequest",
    {"http_method": str, "relative_uri": str, "body": str},
    total=False,
)
Task = TypedDict(
    "Task", {"name": str, "app_engine_http_request": AppEngineHttpRequest}, total=False
)


@attr.s(auto_attribs=True)
class QueueInfo:
    name: str
    region: str


@attr.s(auto_attribs=True)
class AwsCredentials:
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_session_token: str

    def get_dict(self) -> Dict[str, str]:
        return {
            "aws_access_key_id": self.aws_access_key_id,
            "aws_secret_access_key": self.aws_secret_access_key,
            "aws_session_token": self.aws_session_token,
        }


@attr.s(auto_attribs=True)
class AwsS3Object:
    bucket: str
    key: str

    def get_dict(self) -> Dict[str, str]:
        return {"bucket": self.bucket, "key": self.key}


class UploadPayload:
    def __init__(
        self,
        aws_credentials: AwsCredentials,
        aws_s3_object: AwsS3Object,
        gcs_blob: GcsBlob,
    ) -> None:
        self.aws_credentials = aws_credentials
        self.aws_s3_object = aws_s3_object
        self.gcs_blob = gcs_blob

    def __str__(self) -> str:
        return json.dumps(self.get_dict())

    def get_dict(self) -> Dict[str, Dict[str, str]]:
        """
        Gets the `dict` payload to use as the request body when submitting the task,
        e.g.
        ```
        {
            "aws_credentials": {
                "aws_access_key_id": "foo",
                "aws_secret_access_key": "bar",
                "aws_session_token": "baz",
            },
            "aws_s3_object": {"bucket": "s3", "key": "object"},
            "gcs_blob": {"bucket": "cool", "name": "object"},
        }
        ```
        """
        return {
            "aws_credentials": self.aws_credentials.get_dict(),
            "aws_s3_object": self.aws_s3_object.get_dict(),
            "gcs_blob": {
                "bucket": self.gcs_blob.bucket.name,
                "name": self.gcs_blob.name,
            },
        }

    def get_json_string(self) -> str:
        """
        Return the encoded, JSON-serialized representation of the object
        """
        return json.dumps(self.get_dict())

    def get_task_id(self) -> str:
        """
        Returns the md5 hash of the payload as a serialized JSON string. This is useful
        for task deduplication on the queue.
        """
        return md5(self.get_json_string().encode()).hexdigest()


class CloudTasksUploadClient:
    """
    Helper class for submitting upload tasks to Google Cloud Tasks
    """

    def __init__(
        self, queue_info: QueueInfo, log_file_path="accession.log", no_log_file=False
    ) -> None:
        """
        `location` and `queue` refer to the region and name of the queue, respectively.
        """
        self.queue_info = queue_info
        self._client = None
        self._project_id: Optional[str] = None
        self._logger: Optional[logging.Logger] = None
        self.log_file_path = log_file_path
        self.no_log_file = no_log_file

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
    def project_id(self) -> str:
        """
        Raises `ValueError` if `google.auth.default()` cannot determine the project.
        """
        if self._project_id is None:
            _, project_id = google.auth.default()
            if project_id is None:
                raise ValueError(
                    (
                        "Could not determine project ID, try setting with `gcloud "
                        "config set project [PROJECT ID]`"
                    )
                )
            self._project_id = project_id
        return self._project_id

    @property
    def client(self) -> tasks_v2.CloudTasksClient:
        """
        Create a Cloud Tasks client, see
        https://googleapis.dev/python/cloudtasks/latest/gapic/v2/api.html
        """
        if self._client is None:
            self._client = tasks_v2.CloudTasksClient()
        return self._client

    def get_queue_path(self) -> str:
        """
        Return the fully qualified path to the queue.
        """
        return self.client.queue_path(
            project=self.project_id,
            location=self.queue_info.region,
            queue=self.queue_info.name,
        )

    def _get_task_name(self, payload: UploadPayload) -> str:
        """
        Return the properly formatted name of the task using the task's id. This isn't
        a method of UploadPayload because it's not a part of the request body that is
        sent to the upload endpoint and because knowledge of the queue info is required.
        """
        return f"{self.get_queue_path()}/tasks/{payload.get_task_id()}"

    def upload(self, payload: UploadPayload) -> None:
        """
        Wrapper to submit the payload to the upload endpoint, assumed to be `/upload`
        """
        self._submit_task(APP_ENGINE_UPLOAD_ENDPOINT, payload)

    def _submit_task(self, task_endpoint: str, payload: UploadPayload) -> None:
        """
        Given a `dict` payload to submit to Cloud Tasks, creates a new Cloud Tasks
        payload, inserts the necessary fields including the encoded request body, and
        submits the task. It is asssumed here that the task is triggered via a POST
        request to an App Engine endpoint.
        """
        parent = self.get_queue_path()
        task: Task = {
            "name": self._get_task_name(payload),
            "app_engine_http_request": {
                "body": payload.get_json_string(),
                "http_method": "POST",
                "relative_uri": task_endpoint,
            },
        }

        try:
            cloud_task = self.client.create_task(parent, task)
        except ValueError:
            self.logger.exception("Could not create task due to invalid parameters")
            raise
        except GoogleAPICallError as google_api_call_error:
            self.logger.exception(
                "Could not create task due to API error, original message: %s",
                google_api_call_error.message,
            )
            raise
        except RetryError as retry_error:
            self.logger.exception(
                "Could not create task due to Google API retries exceeded, original message: %s",
                retry_error.message,
            )
            raise
        else:
            self.logger.info(
                "Successfully created task %s targeting %s",
                cloud_task.name,
                task_endpoint,
            )
