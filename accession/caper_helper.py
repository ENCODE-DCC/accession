from pathlib import Path
from typing import Any, Dict, List, Optional

from caper.caper_args import DEFAULT_CAPER_CONF, get_parser_and_defaults
from caper.caper_labels import CaperLabels
from caper.cromwell_rest_api import CromwellRestAPI


class CaperHelper:
    """
    Wrapper class around Caper's CromwellRestAPI, since we only need the ability to
    query Cromwell for metadata.
    """

    def __init__(self) -> None:
        self._client: Optional[CromwellRestAPI] = None

    @property
    def client(self) -> CromwellRestAPI:
        if self._client is None:
            _, conf = get_parser_and_defaults(conf_file=DEFAULT_CAPER_CONF)
            self._client = CromwellRestAPI(hostname=conf["hostname"], port=conf["port"])
        return self._client

    def metadata(self, workflow_ids_or_labels: List[str]) -> List[Dict[str, Any]]:
        """
        Don't use the CaperClient here since there is extra stuff in there that we don't
        want or need. The implementation here is copied from
        `caper.caper_client.CaperClient.metadata`, see
        https://github.com/ENCODE-DCC/caper/blob/v1.0.0/caper/caper_client.py
        """
        metadata_results = self.client.get_metadata(
            workflow_ids_or_labels,
            [(CaperLabels.KEY_CAPER_STR_LABEL, v) for v in workflow_ids_or_labels],
            embed_subworkflow=True,
        )
        return metadata_results


def caper_conf_exists() -> bool:
    """
    The DEFAULT_CAPER_CONF looks like `~/.caper/default.conf`, need to expand to the
    user's home directory.
    """
    caper_conf = Path(DEFAULT_CAPER_CONF)
    return caper_conf.expanduser().exists()
