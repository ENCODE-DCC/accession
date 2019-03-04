import argparse
from accession.accession import Accession
from accession.helpers import filter_outputs_by_path


def main(args):
    if args.get('filter_from_path'):
        filter_outputs_by_path(args.get('filter_from_path'))
        return
    accession_steps = args.get('accession_steps')
    accession_metadata = args.get('accession_metadata')
    lab = args.get('lab')
    award = args.get('award')
    server = args.get('server')
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
    args = parser.parse_args()
    main(vars(args))
