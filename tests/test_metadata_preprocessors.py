from accession.metadata_preprocessors import HicMetadataPreprocessor


def test_hic_metadata_preprocessor():
    data = {
        "calls": {
            "ScatterAt87_17": [
                {
                    "subWorkflowMetadata": {
                        "calls": {"hic.align": [{"executionStatus": "Done"}]}
                    }
                }
            ],
            "ScatterAt97_21": [
                {
                    "subWorkflowMetadata": {
                        "calls": {
                            "hic.chimeric_sam_nonspecific": [
                                {"executionStatus": "Done"}
                            ]
                        }
                    }
                }
            ],
            "hic.unnaffected": [{"foo": "bar"}],
        }
    }

    preprocessor = HicMetadataPreprocessor()
    result = preprocessor.process(data)
    assert result == {
        "calls": {
            "hic.align": [
                {
                    "subWorkflowMetadata": {
                        "calls": {"hic.align": [{"executionStatus": "Done"}]}
                    }
                }
            ],
            "hic.chimeric_sam": [
                {
                    "subWorkflowMetadata": {
                        "calls": {
                            "hic.chimeric_sam_nonspecific": [
                                {"executionStatus": "Done"}
                            ]
                        }
                    }
                }
            ],
            "hic.unnaffected": [{"foo": "bar"}],
        }
    }
