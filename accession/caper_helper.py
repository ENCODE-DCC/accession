from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from caper.caper_args import DEFAULT_CAPER_CONF, get_parser_and_defaults
from caper.caper_labels import CaperLabels
from caper.cromwell_rest_api import CromwellRestAPI, has_wildcard, is_valid_uuid


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
            self._client = CromwellRestAPI(
                hostname=conf.get("hostname") or CromwellRestAPI.DEFAULT_HOSTNAME,
                port=conf.get("port") or CromwellRestAPI.DEFAULT_PORT,
            )
        return self._client

    def metadata(self, workflow_ids_or_labels: List[str]) -> List[Dict[str, Any]]:
        """
        Don't use the CaperClient here since there is extra stuff in there that we don't
        want or need. The implementation here is copied from
        `caper.caper_client.CaperClient.metadata`, see
        https://github.com/ENCODE-DCC/caper/blob/v1.0.0/caper/caper_client.py
        """
        workflow_ids, labels = self._split_workflow_ids_and_labels(
            workflow_ids_or_labels
        )

        return self.client.get_metadata(workflow_ids, labels, embed_subworkflow=True)

    def _split_workflow_ids_and_labels(
        self, workflow_ids_or_labels: List[str]
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        workflow_ids: List[str] = []
        labels: List[Tuple[str, str]] = []

        for query in workflow_ids_or_labels:
            if is_valid_uuid(query):
                workflow_ids.append(query)
            else:
                labels.append((CaperLabels.KEY_CAPER_STR_LABEL, query))
                if has_wildcard(query):
                    workflow_ids.append(query)

        return workflow_ids, labels


def caper_conf_exists() -> bool:
    """
    The DEFAULT_CAPER_CONF looks like `~/.caper/default.conf`, need to expand to the
    user's home directory.
    """
    caper_conf = Path(DEFAULT_CAPER_CONF)
    return caper_conf.expanduser().exists()
