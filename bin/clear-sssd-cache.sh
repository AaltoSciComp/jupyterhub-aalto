#!/bin/bash
set -euo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" || exit ; pwd -P )"
NAMESPACE=${1:-jupyter}
# shellcheck source-path=bin
source "$SCRIPTPATH/_check_namespace.sh"

kubectl exec -n "$NAMESPACE" deploy/jupyterhub -- bash -c "service sssd stop ; rm /var/lib/sss/db/* ; service sssd start ; getent group jupyter-testcourse"
echo "SSSD cache cleared"
