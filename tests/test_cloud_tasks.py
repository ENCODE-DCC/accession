import pytest
from google.api_core.exceptions import GoogleAPICallError, RetryError

from accession.backends import GcsBlob
from accession.cloud_tasks import (
    AwsCredentials,
    AwsS3Object,
    CloudTasksUploadClient,
    QueueInfo,
    UploadPayload,
)


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
    mocker.patch.object(GcsBlob, "__init__", return_value=None)

    class StubBucket:
        name = "bucket"

    mocker.patch.object(
        GcsBlob, "bucket", mocker.PropertyMock(return_value=StubBucket())
    )
    gcs_blob = GcsBlob("name", "bucket")
    gcs_blob.name = "name"
    return UploadPayload(
        aws_credentials=aws_credentials, aws_s3_object=aws_s3_object, gcs_blob=gcs_blob
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
