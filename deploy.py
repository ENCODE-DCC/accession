import argparse
import logging
import textwrap
import time

from googleapiclient import Resource, discovery
from googleapiclient.http import HttpError

DEBIAN_10_IMAGE = "projects/debian-cloud/global/images/debian-10-buster-v20200714"


class GcloudClient:
    def __init__(self, project: str) -> None:
        self.project = project
        self._compute = None

    @property
    def compute(self) -> Resource:
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
            "networkInterfaces": [{"network": "global/networks/default"}],
            "metadata": {"items": [{"key": "startup-script", "value": startup_script}]},
        }

        self.compute.instances().insert(
            project=self.project, zone=zone, body=config
        ).execute()

    def _wait_for_operation(self, zone: str, operation: str) -> None:
        logging.info("Waiting for operation to finish...")
        while True:
            result = (
                self.compute.zoneOperations()
                .get(project=self.project, zone=zone, operation=operation)
                .execute()
            )

            if result["status"] == "DONE":
                if "error" in result:
                    raise Exception(result["error"])
                return

            time.sleep(1)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = get_parser()
    args = parser.parse_args()
    client = GcloudClient(args.project_id)
    client.create_firewall_rule()
    client.create_instance(args.zone, args.instance_name)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="Your Google Cloud project ID.")
    parser.add_argument(
        "--zone", default="us-west1-a", help="Compute Engine zone to deploy to."
    )
    parser.add_argument(
        "--instance-name", default="accession", help="The name for the new instance."
    )
    return parser


if __name__ == "__main__":
    main()
