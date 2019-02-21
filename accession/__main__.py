import argparse
from accession.accession import Accession
from accession.helpers import filter_outputs_by_path

if __name__ == '__main__':
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
                        help='path to an accessioning steps')
    parser.add_argument('--server',
                        default='dev',
                        help='Server files will be accessioned to')
    parser.add_argument('--lab',
                        type=str,
                        default=None,
                        help='Lab')
    parser.add_argument('--award',
                        type=str,
                        default=None,
                        help='Award')
    args = parser.parse_args()
    if args.filter_from_path:
        filter_outputs_by_path(args.filter_from_path)

    if (args.accession_steps and args.accession_metadata
            and args.lab and args.award):
        accessioner = Accession(args.accession_steps,
                                args.accession_metadata,
                                args.server,
                                args.lab,
                                args.award)
        accessioner.accession_steps()
