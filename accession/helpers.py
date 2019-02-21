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