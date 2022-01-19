from copy import deepcopy
from typing import Any, Dict

from accession.metadata import MetadataPreprocessor


class HicMetadataPreprocessor(MetadataPreprocessor):
    def process(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        new_metadata = deepcopy(metadata)
        for call_name, calls in metadata["calls"].items():
            if "Scatter" in call_name:
                subworkflow_call_keys = calls[0]["subWorkflowMetadata"]["calls"].keys()
                if "hic.align" in subworkflow_call_keys:
                    new_metadata["calls"]["hic.align"] = calls
                    del new_metadata["calls"][call_name]
                for key in (
                    "hic.chimeric_sam_specific",
                    "hic.chimeric_sam_nonspecific",
                ):
                    if key in subworkflow_call_keys:
                        new_metadata["calls"]["hic.chimeric_sam"] = calls
                        del new_metadata["calls"][call_name]
        return new_metadata
