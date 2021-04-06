import pytest
from google.api_core.exceptions import GoogleAPICallError, NotFound, RetryError

from accession.cloud_tasks import (
    AwsCredentials,
    AwsS3Object,
    CloudTasksUploadClient,
    QueueInfo,
    UploadPayload,
)
from accession.file import GSFile


@pytest.fixture
def aws_credentials():
    return AwsCredentials(
        aws_access_key_id="foo", aws_secret_access_key="bar", aws_session_token="baz"
    )


@pytest.fixture
def aws_s3_object():
    return AwsS3Object(bucket="foo", key="bar")


@pytest.fixture
def upload_payload(mocker, aws_credentials, aws_s3_object):
    blob = mocker.Mock()
    blob.name = "name"
    blob.bucket.name = "bucket"
    mocker.patch("accession.file.GSFile.blob", mocker.PropertyMock(return_value=blob))
    gs_file = GSFile(key="foo", name="gs://bucket/name")
    return UploadPayload(
        aws_credentials=aws_credentials, aws_s3_object=aws_s3_object, gcs_blob=gs_file
    )


@pytest.fixture
def cloud_tasks_upload_client(mocker):
    mocker.patch(
        "accession.cloud_tasks.CloudTasksUploadClient.client",
        new_callable=mocker.PropertyMock(),
    )
    mocker.patch(
        "accession.cloud_tasks.CloudTasksUploadClient.logger",
        new_callable=mocker.PropertyMock(),
    )
    client = CloudTasksUploadClient(
        QueueInfo(region="us-west1", name="queue"), no_log_file=True
    )
    return client


def test_queue_info_from_env(mocker):
    mocker.patch.dict(
        "os.environ",
        {
            "ACCESSION_CLOUD_TASKS_QUEUE_NAME": "foo",
            "ACCESSION_CLOUD_TASKS_QUEUE_REGION": "bar",
        },
    )
    result = QueueInfo.from_env()
    assert result == QueueInfo(name="foo", region="bar")


def test_queue_info_from_env_env_vars_not_set_returns_none(mocker):
    mocker.patch.dict("os.environ", {"ACCESSION_CLOUD_TASKS_QUEUE_NAME": "foo"})
    result = QueueInfo.from_env()
    assert result is None


def test_aws_credentials_get_dict(aws_credentials):
    result = aws_credentials.get_dict()
    assert result == {
        "aws_access_key_id": "foo",
        "aws_secret_access_key": "bar",
        "aws_session_token": "baz",
    }


def test_aws_s3_object_get_dict(aws_s3_object):
    result = aws_s3_object.get_dict()
    assert result == {"bucket": "foo", "key": "bar"}


def test_upload_payload_get_dict(upload_payload):
    result = upload_payload.get_dict()
    assert result["aws_s3_object"]
    assert result["aws_credentials"]
    assert result["gcs_blob"]["bucket"] == "bucket"
    assert result["gcs_blob"]["name"] == "name"


def test_upload_payload_get_bytes(upload_payload):
    result = upload_payload.get_bytes()
    assert result.startswith(b'{"aws_credentials"')


def test_upload_payload_get_task_id(upload_payload):
    result = upload_payload.get_task_id()
    assert result == "127ba03ad0ee8f4fcfe64a9172507e66"


def test_cloud_tasks_upload_client_project_id(mocker, cloud_tasks_upload_client):
    mocker.patch("google.auth.default", return_value=("foo", "project-id"))
    result = cloud_tasks_upload_client.project_id
    assert result == "project-id"


def test_cloud_tasks_upload_client_project_id_google_auth_returns_none_raises(
    mocker, cloud_tasks_upload_client
):
    mocker.patch("google.auth.default", return_value=("foo", None))
    with pytest.raises(ValueError):
        _ = cloud_tasks_upload_client.project_id


def test_cloud_tasks_upload_client_get_queue_path(mocker, cloud_tasks_upload_client):
    mocker.patch("google.auth.default", return_value=("foo", "project-id"))
    cloud_tasks_upload_client.get_queue_path()
    assert cloud_tasks_upload_client.client.queue_path.called_once_with(
        "project-id", "us-west1", "queue"
    )


def test_cloud_tasks_upload_client_validate_queue_info(
    mocker, cloud_tasks_upload_client
):
    mocker.patch.object(cloud_tasks_upload_client, "get_queue_path")
    cloud_tasks_upload_client.validate_queue_info()
    cloud_tasks_upload_client.get_queue_path.assert_called_once()
    cloud_tasks_upload_client.client.get_queue.assert_called_once()


def test_cloud_tasks_upload_client_validate_queue_info_raises(
    mocker, cloud_tasks_upload_client
):
    mocker.patch.object(cloud_tasks_upload_client, "get_queue_path")
    cloud_tasks_upload_client.client.get_queue.side_effect = NotFound(message="failed")
    with pytest.raises(ValueError):
        cloud_tasks_upload_client.validate_queue_info()


def test_cloud_tasks_upload_client_get_task_name(
    mocker, cloud_tasks_upload_client, upload_payload
):
    mocker.patch.object(cloud_tasks_upload_client, "get_queue_path", return_value="foo")
    mocker.patch.object(upload_payload, "get_task_id", return_value="123")
    result = cloud_tasks_upload_client._get_task_name(upload_payload)
    assert result == "foo/tasks/123"


def test_cloud_tasks_upload_client_upload(
    mocker, cloud_tasks_upload_client, upload_payload
):
    mocker.patch.object(cloud_tasks_upload_client, "_submit_task")
    cloud_tasks_upload_client.upload(upload_payload)
    assert cloud_tasks_upload_client._submit_task.called_once_with(
        "/upload", upload_payload
    )


def test_cloud_tasks_upload_client_submit_task(
    mocker, cloud_tasks_upload_client, upload_payload
):
    mocker.patch.object(
        cloud_tasks_upload_client, "get_queue_path", return_value="queue-path"
    )
    cloud_tasks_upload_client._submit_task("/endpoint", upload_payload)
    assert cloud_tasks_upload_client.client.create_task.called_once_with(
        "queue-path", upload_payload
    )
    assert cloud_tasks_upload_client.logger.info.call_args[0][2] == "/endpoint"


def test_cloud_tasks_upload_client_submit_task_value_error(
    mocker, cloud_tasks_upload_client, upload_payload
):
    mocker.patch.object(
        cloud_tasks_upload_client, "get_queue_path", return_value="queue-path"
    )
    mocker.patch.object(
        cloud_tasks_upload_client.client, "create_task", side_effect=ValueError("error")
    )
    with pytest.raises(ValueError):
        try:
            cloud_tasks_upload_client._submit_task("/endpoint", upload_payload)
        finally:
            assert cloud_tasks_upload_client.logger.exception.called_once()


def test_cloud_tasks_upload_client_submit_task_google_api_call_error(
    mocker, cloud_tasks_upload_client, upload_payload
):
    mocker.patch.object(
        cloud_tasks_upload_client, "get_queue_path", return_value="queue-path"
    )
    mocker.patch.object(
        cloud_tasks_upload_client.client,
        "create_task",
        side_effect=GoogleAPICallError(message="foo"),
    )
    with pytest.raises(GoogleAPICallError):
        try:
            cloud_tasks_upload_client._submit_task("/endpoint", upload_payload)
        finally:
            assert cloud_tasks_upload_client.logger.exception.call_args[0][1] == "foo"


def test_cloud_tasks_upload_client_submit_task_retry_error(
    mocker, cloud_tasks_upload_client, upload_payload
):
    mocker.patch.object(
        cloud_tasks_upload_client, "get_queue_path", return_value="queue-path"
    )
    mocker.patch.object(
        cloud_tasks_upload_client.client,
        "create_task",
        side_effect=RetryError(message="foo", cause=Exception("bar")),
    )
    with pytest.raises(RetryError):
        try:
            cloud_tasks_upload_client._submit_task("/endpoint", upload_payload)
        finally:
            assert cloud_tasks_upload_client.logger.exception.call_args[0][1] == "foo"
