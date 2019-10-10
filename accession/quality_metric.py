class QualityMetric(object):
    """docstring for QualityMetric"""

    def __init__(self, payload, file_id):
        super().__init__()
        if not file_id:
            raise "QC metric needs an accessioned file"
        self.files = [file_id]
        self.payload = payload
