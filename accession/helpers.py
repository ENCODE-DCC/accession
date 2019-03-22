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


def mutate_digits(md5sum_string):
    md5sum_list = list(md5sum_string)
    for i, character in enumerate(md5sum_list):
        print(i)
        print(character)
        if character.isdigit():
            if random.choice([True, False]):
                continue
            md5sum_list[i] = str((int(character) + 1) % 10)
        print(md5sum_list)
    return ''.join(md5sum_list)
