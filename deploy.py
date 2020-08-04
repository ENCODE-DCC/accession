import argparse
import logging
import textwrap

from googleapiclient import discovery
from googleapiclient.http import HttpError

DEBIAN_10_IMAGE = "projects/debian-cloud/global/images/debian-10-buster-v20200714"


class GcloudClient:
    def __init__(self, project: str) -> None:
        self.project = project
        self._compute = None

    @property
    def compute(self) -> discovery.Resource:
        if self._compute is None:
            self._compute = discovery.build("compute", "v1")
        return self._compute

    def create_firewall_rule(self) -> None:
        """
        Idempotently creates a firewall rule allowing TCP traffic on port 8000 from
        instances with tag `accessioning` into instances with tag `caper-server`.
        """
        logging.info("Creating firewall rule")
        rule_name = "accession-remote-caper"
        firewall_body = {
            "name": rule_name,
            "allowed": [{"IPProtocol": "tcp", "ports": ["8000"]}],
            "sourceTags": ["accessioning"],
            "targetTags": ["caper-server"],
        }
        request = self.compute.firewalls().insert(
            project=self.project, body=firewall_body
        )
        try:
            request.execute()
        except HttpError:
            logging.warn("Firewall rule %s already exists, skipping", rule_name)

    def create_instance(self, zone, instance_name: str) -> None:
        logging.info("Creating instance %s", instance_name)
        startup_script = textwrap.dedent(
            """
            sudo apt-get update
            sudo apt-get install -y python3-pip
            sudo pip3 install -U accession
        """
        )

        config = {
            "name": instance_name,
            "machineType": f"zones/{zone}/machineTypes/n1-standard-4",
            "disks": [
                {
                    "boot": True,
                    "autoDelete": True,
                    "initializeParams": {"sourceImage": DEBIAN_10_IMAGE},
                }
            ],
            "networkInterfaces": [
                {
                    "network": "global/networks/default",
                    "accessConfigs": [
                        {"type": "ONE_TO_ONE_NAT", "name": "External NAT"}
                    ],
                }
            ],
            "serviceAccounts": [
                {
                    "email": "default",
                    "scopes": ["https://www.googleapis.com/auth/logging.write"],
                }
            ],
            "metadata": {"items": [{"key": "startup-script", "value": startup_script}]},
            "tags": {"items": ["accessioning"]},
        }

        self.compute.instances().insert(
            project=self.project, zone=zone, body=config
        ).execute()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    parser = get_parser()
    args = parser.parse_args()
    client = GcloudClient(args.project)
    client.create_firewall_rule()
    client.create_instance(args.zone, args.instance_name)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p",
        "--project",
        help="The Google Cloud project ID in which the instance will be deployed",
    )
    parser.add_argument(
        "-z",
        "--zone",
        default="us-west1-a",
        help="The Compute Engine zone to deploy to.",
    )
    parser.add_argument(
        "-n",
        "--instance-name",
        default="accession",
        help="The name for the new instance.",
    )
    return parser


if __name__ == "__main__":
    main()
