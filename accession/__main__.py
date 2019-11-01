import argparse

from accession.accession import Accession
from accession.accession import AccessionSteps
from accession.analysis import Analysis
from accession.analysis import MetaData
from accession.helpers import filter_outputs_by_path

from encode_utils.connection import Connection


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
    return parser


def main(args=None):
    parser = get_parser()
    args = parser.parse_args(args)

    if args.filter_from_path:
        filter_outputs_by_path(args.filter_from_path)
        return
    metadata = MetaData(args.accession_metadata)
    accession_steps = AccessionSteps(args.accession_steps)
    analysis = Analysis(metadata)
    connection = Connection(args.server)
    lab = args.lab
    award = args.award
    if all([accession_steps, analysis, lab, award, connection]):
        accessioner = Accession(accession_steps, analysis, connection, lab, award)
        accessioner.accession_steps()
        return
    print("Module called without proper arguments")


if __name__ == "__main__":
    main()
