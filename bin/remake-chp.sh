#!/bin/bash
set -uo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" || exit ; pwd -P )"

kubectl delete -f "$SCRIPTPATH/../k8s-yaml/chp.yaml"
kubectl create -f "$SCRIPTPATH/../k8s-yaml/chp.yaml"
