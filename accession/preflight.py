import logging
from typing import List, Optional

import attr

from accession.encode_models import EncodeFile


@attr.s(auto_attribs=True)
class MatchingMd5Record:
    gs_file_path: str
    portal_files: List[EncodeFile]


class PreflightHelper:
    """
    Encapsulates some helper functions used for doing dry run reporting, consumes data
    fed to it by the Accession instance and logs formatted messages.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def make_file_matching_md5_record(
        self, filename: str, matching: List[EncodeFile]
    ) -> Optional[MatchingMd5Record]:
        """
        Returns a record of all portal files with a matching md5sum, or None if no
        matching files were found.
        """
        if not matching:
            return None
        matching_md5_record = MatchingMd5Record(
            gs_file_path=filename, portal_files=matching
        )
        return matching_md5_record

    def make_log_messages_from_records(
        self, matches: List[MatchingMd5Record]
    ) -> List[str]:
        header = (
            "File Path",
            "Matching Portal Files",
            "Portal Status",
            "Portal File Dataset",
        )
        rows = [header]
        for match in matches:
            for i, portal_file in enumerate(match.portal_files):
                if i == 0:
                    display_filename = match.gs_file_path
                else:
                    display_filename = ""
                rows.append(
                    (
                        display_filename,
                        portal_file.accession,
                        portal_file.status,
                        portal_file.dataset,
                    )
                )
        columns = list(zip(*rows))
        column_widths = []
        for column in columns:
            lens = [len(i) for i in column]
            column_widths.append(max(lens))
        template = "{{:{}}} | {{:{}}} | {{:{}}} | {{:{}}}".format(*column_widths)
        messages = [template.format(*row) for row in rows]
        return messages

    def report_dry_run(self, matches: List[MatchingMd5Record]) -> None:
        """
        Print the report for the dry run. We use a format string to control the width
        for each column by adding padding where appropriate. The column width is
        governed by the length (in characters) of the longest element in each column.
        When there is more than one file at the portal that had a matching md5sum, the
        file path is not printed for subsequent report rows after the first match for
        visual clarity.
        """
        if not matches:
            self.logger.info("No MD5 conflicts found.")
            return
        else:
            self.logger.info("Found files with duplicate md5sums")
        messages = self.make_log_messages_from_records(matches)
        for msg in messages:
            self.logger.info(msg)
