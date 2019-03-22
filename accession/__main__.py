import argparse
from accession.accession import Accession
from accession.helpers import filter_outputs_by_path


def get_parser():
    parser = argparse.ArgumentParser(description="Accession pipeline outputs, \
                                                 download output metadata for scattering")
    parser.add_argument('--filter-from-path',
                        type=str,
                        default=None,
                        help='path to a folder with pipeline run outputs')
    parser.add_argument('--accession-metadata',
                        type=str,
                        default=None,
                        help='path to a metadata json output file')
    parser.add_argument('--accession-steps',
                        type=str,
                        default=None,
                        help='path to an accessioning steps, json file')
    parser.add_argument('--server',
                        default='dev',
                        help='Server the files will be accessioned to')
    parser.add_argument('--lab',
                        type=str,
                        default=None,
                        help='Lab')
    parser.add_argument('--award',
                        type=str,
                        default=None,
                        help='Award')
    return parser


def main(args=None):
    parser = get_parser()
    args = parser.parse_args(args)

    if args.filter_from_path:
        filter_outputs_by_path(args.filter_from_path)
        return
    accession_steps = args.accession_steps
    accession_metadata = args.accession_metadata
    lab = args.lab
    award = args.award
    server = args.server
    if all([accession_steps,
            accession_metadata,
            lab,
            award,
            server]):
        accessioner = Accession(accession_steps,
                                accession_metadata,
                                server,
                                lab,
                                award)
        accessioner.accession_steps()
        return
    print("Module called without proper arguments")


if __name__ == '__main__':
    main()
