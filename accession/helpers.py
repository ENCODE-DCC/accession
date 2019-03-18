import tempfile
import json
import random
from accession.backends import GCBackend


def filter_outputs_by_path(path):
    bucket = path.split('gs://')[1].split('/')[0]
    google_backend = GCBackend(bucket)
    filtered = [file
                for file
                in list(google_backend.bucket.list_blobs())

                if path.split('gs://')[1]
                in file.id
                and '.json' in file.id]

    for file in filtered:
        file.download_to_filename(file.public_url.split('/')[-1])


# Python equivalent of WDL's write_json
# for testing purposes
def write_json(json_data):
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    with open(temp_file.name, 'a') as file:
        json.dump(json_data, file)
    return temp_file.name


def mutate_md5sum(md5sum_string):
    for i in range(len(md5sum_string)):
        if isinstance(md5sum_string[i], int):
            if random.choice([True, False]):
                continue
            md5sum_string[i] = (md5sum_string[i] + 1) % 10
    return md5sum_string
