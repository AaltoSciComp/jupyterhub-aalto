#!/bin/bash
set -euo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

kubectl delete -f $SCRIPTPATH/../k8s-yaml/chp.yaml
kubectl create -f $SCRIPTPATH/../k8s-yaml/chp.yaml
