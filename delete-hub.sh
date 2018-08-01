SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

kubectl delete configmap jupyterhub-config
kubectl delete -f $SCRIPTPATH/jupyterhub.yaml
