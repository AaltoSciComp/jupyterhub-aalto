SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
cd $SCRIPTPATH/../
NAMESPACE=${1:-jupyter}
echo "Namespace: $NAMESPACE"

kubectl delete secret -n $NAMESPACE tls
kubectl create secret -n $NAMESPACE tls tls --cert=secrets/jupyter_cs_aalto_fi.crt --key=secrets/jupyter.cs.aalto.fi.key

kubectl delete secret -n $NAMESPACE adpw.txt
kubectl create secret -n $NAMESPACE generic adpw.txt --from-file=secrets/adpw.txt

kubectl delete secret -n $NAMESPACE localusers
kubectl create secret -n $NAMESPACE generic localusers --from-file=secrets/localusers.sh

kubectl delete secret -n $NAMESPACE chp-secret
kubectl create secret -n $NAMESPACE generic chp-secret --from-file=secrets/chp-secret.txt

kubectl delete secret -n $NAMESPACE idrsa
kubectl create secret -n $NAMESPACE generic idrsa --from-file=secrets/id_rsa_hub
kubectl delete secret -n $NAMESPACE idrsapub
kubectl create secret -n $NAMESPACE generic idrsapub --from-file=secrets/id_rsa_hub.pub
kubectl delete secret -n $NAMESPACE knownhosts
kubectl create secret -n $NAMESPACE generic knownhosts --from-file=secrets/known_hosts
