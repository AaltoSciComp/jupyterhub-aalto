SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

kubectl delete configmap jupyterhub-config
kubectl delete -f $SCRIPTPATH/jupyterhub.yaml
kubectl delete configmap hub-status-service

# Delete non-stopping pods:
# kubectl delete pod --force --grace-period=0 `kubectl get pods | grep Termin | grep jupyterhub | cut -d\  -f1`

