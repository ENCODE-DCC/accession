import json
import tempfile
from abc import ABC, abstractmethod
from base64 import b64decode
from typing import Optional

from google.cloud import storage


class BackendBase(ABC):
    @property
    @abstractmethod
    def scheme(self):
        raise NotImplementedError("Concrete subclasses need to specify a URI scheme")


class GCBackend(BackendBase):
    """
    Backend for interacting with Google Cloud Storage (GCS)
    """

    def __init__(self, bucket):
        self.client = storage.Client()
        self.bucket = self.client.get_bucket(bucket)
        self.local_mapping = {}

    @property
    def scheme(self) -> str:
        return "gs://"

    def blob_from_filename(self, filename):
        bucket_name = filename.split(self.scheme)[1].split("/")[0]
        # Reference genome may reside in different buckets
        if self.bucket.name != bucket_name:
            bucket = self.client.get_bucket(bucket_name)
        else:
            bucket = self.bucket
        blob = GcsBlob(self.file_path(filename, bucket), bucket)
        blob.reload()
        return blob

    def file_path(self, file, bucket):
        """
        File path without bucket name
        """
        file_path = file.split("{}{}/".format(self.scheme, bucket.name))[1]
        return file_path

    def read_file(self, file):
        """
        Downloads file as bytes (despite the name of blob's method)
        """
        blob = self.blob_from_filename(file)
        return blob.download_as_string()

    def read_json(self, file):
        """
        Read json file
        """
        return json.loads(self.read_file(file.filename).decode())

    def download(self, file):
        """
        Downloads file to local filesystem using a tempfile
        """
        blob = self.blob_from_filename(file)
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        with open(temp_file.name, "wb"):
            blob.download_to_filename(temp_file.name)
        self.local_mapping[file] = [temp_file.name, self.md5_from_blob(blob)]
        return self.local_mapping[file]


class GcsBlob(storage.blob.Blob):
    """
    Wrapper around GCS blob class to better map to portal metadata. This class is not
    intended to be initialized directy, instead use `GCBackend.blob_from_filename()` to
    obtain the blob
    """

    def __init__(self, *args, **kwargs):
        """
        Initializes self.pos to 0 for keeping track of number of bytes read from file.
        """
        self.pos = 0
        super().__init__(*args, **kwargs)

    @property
    def md5sum(self) -> str:
        """
        Returns md5sum of the file in hex. Need to wrap around gcloud API's md5sums,
        which are returned as base64, to match ENCODE portal md5sums.
        """
        return b64decode(super().md5_hash).hex()

    def read(self, num_bytes: Optional[int] = None) -> bytes:
        """
        Method to enable using boto3 for uploading files without downloading to disk.
        `Blob.download_as_string()` takes `start` and `end` kwargs to specify a byte
        range. These are 0-indexed and inclusive of endpoints. If the position is
        greater than or equal to the size of the object then we treat that as EOF and
        return an empty byte string `b''`.

        See https://googleapis.dev/python/storage/latest/blobs.html#google.cloud.storage.blob.Blob.download_as_string
        and https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.upload_fileobj
        """
        if num_bytes is None:
            return self.download_as_string()
        else:
            if self.pos >= self.size:
                read_bytes = b""
            else:
                read_bytes = self.download_as_string(
                    start=self.pos, end=self.pos + num_bytes - 1
                )
                self.pos += num_bytes
            return read_bytes
