SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

kubectl create configmap jupyterhub-config --from-file=$SCRIPTPATH/jupyterhub_config.py
kubectl create -f $SCRIPTPATH/jupyterhub.yaml
