import argparse
import os
from typing import Optional, Tuple

from encode_utils.connection import Connection

from accession import __version__
from accession.accession import Accession, AccessionSteps
from accession.analysis import Analysis, MetaData
from accession.helpers import filter_outputs_by_path


def get_parser():
    parser = argparse.ArgumentParser(
        description="Accession pipeline outputs, \
                                                 download output metadata for scattering"
    )
    parser.add_argument(
        "--filter-from-path",
        type=str,
        default=None,
        help="path to a folder with pipeline run outputs",
    )
    parser.add_argument(
        "--accession-metadata",
        type=str,
        default=None,
        help="path to a metadata json output file",
    )
    parser.add_argument(
        "--accession-steps",
        type=str,
        default=None,
        help="path to an accessioning steps, json file",
    )
    parser.add_argument(
        "--server", default="dev", help="Server the files will be accessioned to"
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


def main(args=None):
    parser = get_parser()
    args = parser.parse_args(args)
    lab, award = check_or_set_lab_award(args.lab, args.award)
    if args.filter_from_path:
        filter_outputs_by_path(args.filter_from_path)
        return
    metadata = MetaData(args.accession_metadata)
    accession_steps = AccessionSteps(args.accession_steps)
    analysis = Analysis(metadata)
    connection = Connection(args.server)
    if all([accession_steps, analysis, lab, award, connection]):
        accessioner = Accession(accession_steps, analysis, connection, lab, award)
        accessioner.accession_steps()
        return
    print("Module called without proper arguments")


if __name__ == "__main__":
    main()
