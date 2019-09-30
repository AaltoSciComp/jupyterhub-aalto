SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

kubectl create configmap jupyterhub-config -n jupyter --from-file=$SCRIPTPATH/../jupyterhub_config.py
kubectl create configmap hub-status-service -n jupyter --from-file=$SCRIPTPATH/../scripts/hub_status_service.py
kubectl create configmap cull-idle-servers -n jupyter --from-file=$SCRIPTPATH/../scripts/cull_idle_servers.py
kubectl create configmap spawn-test -n jupyter --from-file=$SCRIPTPATH/../bin/spawn_test.py
kubectl create -f $SCRIPTPATH/../k8s-yaml/jupyterhub.yaml
