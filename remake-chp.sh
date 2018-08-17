SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

kubectl delete -f $SCRIPTPATH/chp.yaml
kubectl create -f $SCRIPTPATH/chp.yaml
