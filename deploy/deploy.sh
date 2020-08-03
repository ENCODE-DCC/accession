#! /bin/bash
set -euo pipefail

gcloud compute firewall-rules create accession-remote-caper --allow=tcp:8000 --source-tags=accessioning --target-tags=http-server
