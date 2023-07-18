#!/bin/bash
set -uo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
NAMESPACE=${1:-jupyter}
source "$SCRIPTPATH/_check_namespace.sh"

kubectl delete secret -n $NAMESPACE tls
kubectl create secret -n $NAMESPACE tls tls --cert=$SCRIPTPATH/../secrets/jupyter_cs_aalto_fi.crt --key=$SCRIPTPATH/../secrets/jupyter.cs.aalto.fi.key

kubectl delete secret -n $NAMESPACE adpw.txt
kubectl create secret -n $NAMESPACE generic adpw.txt --from-file=$SCRIPTPATH/../secrets/adpw.txt

kubectl delete secret -n $NAMESPACE localusers
kubectl create secret -n $NAMESPACE generic localusers --from-file=$SCRIPTPATH/../secrets/localusers.sh

kubectl delete secret -n $NAMESPACE chp-secret
kubectl create secret -n $NAMESPACE generic chp-secret --from-file=$SCRIPTPATH/../secrets/chp-secret.txt

kubectl delete secret -n $NAMESPACE ssh-privkey
kubectl create secret -n $NAMESPACE generic ssh-privkey --from-file=$SCRIPTPATH/../secrets/ssh_key
kubectl delete secret -n $NAMESPACE ssh-pubkey
kubectl create secret -n $NAMESPACE generic ssh-pubkey --from-file=$SCRIPTPATH/../secrets/ssh_key.pub
kubectl delete secret -n $NAMESPACE knownhosts
kubectl create secret -n $NAMESPACE generic knownhosts --from-file=$SCRIPTPATH/../secrets/known_hosts
