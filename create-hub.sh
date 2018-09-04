SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

kubectl create configmap jupyterhub-config --from-file=$SCRIPTPATH/jupyterhub_config.py
kubectl create configmap hub-status-service --from-file=$SCRIPTPATH/scripts/hub_status_service.py
kubectl create -f $SCRIPTPATH/jupyterhub.yaml
