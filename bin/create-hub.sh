#!/bin/bash
set -euo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
NAMESPACE=${1:-jupyter}
source "$SCRIPTPATH/_check_namespace.sh"

kubectl create configmap jupyterhub-config -n $NAMESPACE --from-file=$SCRIPTPATH/../jupyterhub_config.py
kubectl create configmap hub-status-service -n $NAMESPACE --from-file=$SCRIPTPATH/../scripts/hub_status_service.py
kubectl create configmap cull-idle-servers -n $NAMESPACE --from-file=$SCRIPTPATH/../scripts/cull_idle_servers.py
kubectl create configmap spawn-test -n $NAMESPACE --from-file=$SCRIPTPATH/../bin/spawn_test.py
kubectl create -f $SCRIPTPATH/../k8s-yaml/jupyterhub.yaml
