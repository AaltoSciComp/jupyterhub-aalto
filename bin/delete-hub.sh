#!/bin/bash
set -uo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" || exit ; pwd -P )"
NAMESPACE=${1:-jupyter-test}
# shellcheck source-path=bin
source "$SCRIPTPATH/_check_namespace.sh"

kubectl delete configmap -n "$NAMESPACE" jupyterhub-config
kubectl delete -f "$SCRIPTPATH/../k8s-yaml/jupyterhub.yaml"
kubectl delete configmap -n "$NAMESPACE" hub-status-service
kubectl delete configmap -n "$NAMESPACE" cull-idle-servers
kubectl delete configmap -n "$NAMESPACE" create-ci-user
kubectl delete configmap -n "$NAMESPACE" spawn-test

# Delete non-stopping pods:
# kubectl delete pod --force --grace-period=0 `kubectl get pods | grep Termin | grep jupyterhub | cut -d\  -f1`

# Wait for stop
echo "Waiting to stop existing pod..."
while kubectl get pods -n "$NAMESPACE" | grep '^jupyterhub-.*Running' ; do
    sleep 1
done
