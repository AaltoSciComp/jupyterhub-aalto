#!/bin/bash
set -euo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
NAMESPACE=${1:-jupyter-test}
# shellcheck source-path=bin
source "$SCRIPTPATH/_check_namespace.sh"

kubectl apply -f "$SCRIPTPATH/../k8s-yaml/namespace.yaml"
kubectl apply -f "$SCRIPTPATH/../k8s-yaml/le-issuer.yaml"
kubectl apply -f "$SCRIPTPATH/../k8s-yaml/ingress.yaml"
kubectl apply -f "$SCRIPTPATH/../k8s-yaml/chp-frame.yaml"
kubectl apply -f "$SCRIPTPATH/../k8s-yaml/jupyterhub-frame.yaml"
kubectl apply -f "$SCRIPTPATH/../k8s-yaml/nfs-storage.yaml"
