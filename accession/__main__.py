import argparse
import os
from typing import Optional, Tuple

from accession import __version__
from accession.accession import accession_factory


def get_parser():
    parser = argparse.ArgumentParser(
        description="Accession pipeline outputs, \
                                                 download output metadata for scattering"
    )
    parser.add_argument(
        "--accession-metadata",
        type=str,
        default=None,
        help="path to a metadata json output file",
    )
    parser.add_argument(
        "--pipeline-type",
        type=str,
        default=None,
        help=f"the type of pipeline run being accessioned, e.g. mirna or long_read_rna",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Perform a dry run for accessioning, not post anything.",
    )
    parser.add_argument(
        "--server", default="dev", help="Server the files will be accessioned to"
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


def main():
    parser = get_parser()
    args = parser.parse_args()
    lab, award = check_or_set_lab_award(args.lab, args.award)
    if all([args.pipeline_type, args.accession_metadata, lab, award, args.server]):
        accessioner = accession_factory(
            args.pipeline_type,
            args.accession_metadata,
            args.server,
            lab,
            award,
            log_file_path=args.log_file_path,
            no_log_file=args.no_log_file,
        )
        accessioner.accession_steps(args.dry_run)
        return
    print("Module called without proper arguments")


if __name__ == "__main__":
    main()
