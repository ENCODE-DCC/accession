import argparse
import os
from enum import Enum
from typing import List, Optional, Tuple

from accession import __version__
from accession.accession import accession_factory
from accession.cloud_tasks import QueueInfo
from accession.database.connection import DbSession
from accession.database.query import DbQuery
from accession.metadata import parse_metadata_list
from accession.subcommands.info import info


class Subparsers(Enum):
    Info = "info"


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Accession pipeline outputs, \
                                                 download output metadata for scattering"
    )
    metadata_group = parser.add_mutually_exclusive_group()
    metadata_group.add_argument(
        "-m",
        "--accession-metadata",
        help="path to a metadata json file or a Caper workflow ID/label",
    )
    metadata_group.add_argument(
        "-l",
        "--metadata-list",
        help="A file containing one or more paths to metadata JSON files or Caper workflow IDs/labels, one per line.",
    )
    parser.add_argument(
        "-p",
        "--pipeline-type",
        type=str,
        default=None,
        help="the type of pipeline run being accessioned, e.g. mirna or long_read_rna",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help=(
            "Perform a dry run for accessioning, not posting anything. Has precedence "
            "over -f/--force"
        ),
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force accessioning to post files even if there is md5 duplication",
    )
    parser.add_argument(
        "-s", "--server", default="dev", help="Server the files will be accessioned to"
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help=(
            "If this flag is specified, don't log to a log file, will still log to "
            "stdout. Will not write to file specified by `--log-file-path`"
        ),
    )
    parser.add_argument(
        "--log-file-path",
        default="accession.log",
        help=(
            "Path to file to write logs to. This will create this file if it does not "
            "exist and append if it already exists."
        ),
    )
    parser.add_argument("--lab", type=str, default=None, help="Lab")
    parser.add_argument("--award", type=str, default=None, help="Award")
    parser.add_argument(
        "-v", "--version", action="version", version="%(prog)s {}".format(__version__)
    )
    subparsers = parser.add_subparsers(title="subcommands", dest="subcommand_name")
    info_parser = subparsers.add_parser(
        name=Subparsers.Info.value,
        help="Obtain accessioning results in a tabular format",
    )
    info_parser.add_argument(
        "-i",
        "--ids",
        help=(
            "One or more experiment accessions or `@id`s, e.g. /experiments/ENCSR123ABC/"
            "or ENCSR456DEF, Cromwell workflow IDs (can specify whole ID or only the "
            "first few digits, a la `git`), `caper-str-label`s, or other Crowmell "
            "workflow labels in key=value form, e.g. my-label=foo. These can be "
            "combined in arbitrary fashion. If no filters are specified, then info "
            "about all accessioning runs will be returned."
        ),
        nargs="+",
    )
    info_parser.add_argument(
        "-d",
        "--date",
        help=(
            "Can be either a single date or a range of dates. Dates should take the "
            "form `MM`, `MM/DD` or `MM/DD/YY`, with zero-padding and year optional. If "
            "the year is left out then the current year will be inserted "
            "automatically. For example, `4/5`, `04/05`, and `4/5/20` are all "
            "equivalent assuming it is 2020. To use a date range, either specify two "
            "valid dates separated by a dash, e.g. `4/5-4/6` or `4-6`, specify one "
            "date with a leading `\\-`, meaning search from the beginning of time to "
            "the provided date, e.g. `\\-4/5/20`, or use a trailing dash to search "
            "from the specifed date to the present."
        ),
    )
    return parser


def check_or_set_lab_award(lab: Optional[str], award: Optional[str]) -> Tuple[str, str]:
    error_msg = (
        "Could not identify {}, make sure you passed in the --{} command line argument"
        "or set the DCC_{} environment variable"
    )
    lab_prop = "lab"
    award_prop = "award"
    if not lab:
        try:
            lab = os.environ[f"DCC_{lab_prop.upper()}"]
        except KeyError as e:
            raise EnvironmentError(
                error_msg.format(lab_prop, lab_prop, lab_prop.upper())
            ) from e
    if not award:
        try:
            award = os.environ[f"DCC_{award_prop.upper()}"]
        except KeyError as e:
            raise EnvironmentError(
                error_msg.format(award_prop, award_prop, award_prop.upper())
            ) from e
    return lab, award


def get_metadatas_from_args(args: argparse.Namespace) -> List[str]:
    """
    If there was only one metadata file/label provided, then returns a list containing
    just that one metadata item, otherwise parses the metadata list file returning the
    list of workflow IDs/labels.
    """
    if args.metadata_list:
        with open(args.metadata_list) as f:
            metadatas = parse_metadata_list(f)
    else:
        metadatas = [args.accession_metadata]
    return metadatas


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()
    lab, award = check_or_set_lab_award(args.lab, args.award)
    queue_info = QueueInfo.from_env()
    if args.accession_metadata is not None or args.metadata_list is not None:
        metadatas = get_metadatas_from_args(args)
        for metadata in metadatas:
            accessioner = accession_factory(
                args.pipeline_type,
                metadata,
                args.server,
                lab,
                award,
                log_file_path=args.log_file_path,
                no_log_file=args.no_log_file,
                queue_info=queue_info,
            )
            if accessioner.cloud_tasks_upload_client is not None:
                accessioner.cloud_tasks_upload_client.validate_queue_info()
            accessioner.accession_steps(args.dry_run, force=args.force)
    elif args.subcommand_name == Subparsers.Info.value:
        session = DbSession.with_home_dir_db_path()
        db_query = DbQuery(session)
        info(db_query, args.ids, args.date)


if __name__ == "__main__":
    main()
