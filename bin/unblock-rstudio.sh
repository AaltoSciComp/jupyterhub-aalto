#!/bin/bash
set -euo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" || exit ; pwd -P )"
NAMESPACE=${1:-jupyter}
# shellcheck source-path=bin
source "$SCRIPTPATH/_check_namespace.sh"

kubectl delete -f "$SCRIPTPATH/../k8s-yaml/ingress-block-rstudio.yaml"
