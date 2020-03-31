import json
import tempfile
from base64 import b64decode

from google.cloud import storage


class GCBackend:
    """docstring for GCBackend"""

    def __init__(self, bucket):
        self.client = storage.Client()
        self.bucket = self.client.get_bucket(bucket)
        self.local_mapping = {}

    def blob_from_filename(self, filename):
        bucket_name = filename.split("gs://")[1].split("/")[0]
        # Reference genome may reside in different buckets
        if self.bucket.name != bucket_name:
            bucket = self.client.get_bucket(bucket_name)
        else:
            bucket = self.bucket
        blob = storage.blob.Blob(self.file_path(filename, bucket), bucket)
        blob.reload()
        return blob

    # Returns md5sum of the file in hex
    def md5sum(self, file):
        blob = self.blob_from_filename(file)
        return self.md5_from_blob(blob)

    def size(self, file):
        blob = self.blob_from_filename(file)
        return blob.size

    # Converts base64 hash to hex format
    def md5_from_blob(self, blob):
        return b64decode(blob.md5_hash).hex()

    # File path without bucket name
    def file_path(self, file, bucket):
        file_path = file.split("gs://{}/".format(bucket.name))[1]
        return file_path

    # Downloads file as bytes (despite the name of blob's method)
    def read_file(self, file):
        blob = self.blob_from_filename(file)
        return blob.download_as_string()

    # Read json file
    def read_json(self, file):
        return json.loads(self.read_file(file.filename).decode())

    # Downloads file to local filesystem
    def download(self, file):
        blob = self.blob_from_filename(file)
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        with open(temp_file.name, "wb"):
            blob.download_to_filename(temp_file.name)
        self.local_mapping[file] = [temp_file.name, self.md5_from_blob(blob)]
        return self.local_mapping[file]
