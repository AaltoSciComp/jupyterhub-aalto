#!/bin/bash
set -euo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" || exit ; pwd -P )"
NAMESPACE=${1:-jupyter-exam1}
# shellcheck source-path=bin
source "$SCRIPTPATH/_check_namespace.sh"

# JMGR_HOSTNAME=root@jupyter-manager-2.cs.aalto.fi

# Syntax check the hub config file first.
if ! python3 -m py_compile "$SCRIPTPATH/../jupyterhub_config.py" ; then
    echo "jupyterhub_config.py has invalid syntax, aborting the hub restart."
    exit
fi

# echo "Stopping hub"
# "$SCRIPTPATH/delete-hub.sh" "$NAMESPACE"
# # sometimes this proxy pid needs deletion... eventually find a better solution.
# if [ "$NAMESPACE" = "jupyter" ]; then
#     JUPYTER_PATH=/mnt/jupyter
# else
#     JUPYTER_PATH="/mnt/jupyter/$NAMESPACE"
# fi
# echo "Running ssh"
# timeout 2 ssh $JMGR_HOSTNAME "rm -f $JUPYTER_PATH/admin/hubdata/jupyterhub-proxy.pid"
# "$SCRIPTPATH/create-directories.sh" "$JUPYTER_PATH" "$JMGR_HOSTNAME"
#
# echo "Starting hub"
# "$SCRIPTPATH/create-hub.sh" "$NAMESPACE"

kubectl create configmap jupyterhub-config -n "$NAMESPACE" --from-file="$SCRIPTPATH/../jupyterhub_config.py" -o yaml --dry-run=client | kubectl apply -f -
kubectl create configmap hub-status-service -n "$NAMESPACE" --from-file="$SCRIPTPATH/../scripts/hub_status_service.py" -o yaml --dry-run=client | kubectl apply -f -
kubectl create configmap cull-idle-servers -n "$NAMESPACE" --from-file="$SCRIPTPATH/../scripts/cull_idle_servers.py" -o yaml --dry-run=client | kubectl apply -f -
kubectl create configmap create-ci-user -n "$NAMESPACE" --from-file="$SCRIPTPATH/../scripts/create_ci_user.py" -o yaml --dry-run=client | kubectl apply -f -
kubectl create configmap nbgrader-randomize-release -n "$NAMESPACE" --from-file="$SCRIPTPATH/../scripts/nbgrader_randomize_release.py" -o yaml --dry-run=client | kubectl apply -f -
kubectl create configmap nbgrader-randomized-fetch -n "$NAMESPACE" --from-file="$SCRIPTPATH/../scripts/nbgrader_randomized_fetch.py" -o yaml --dry-run=client | kubectl apply -f -
kubectl create configmap spawn-test -n "$NAMESPACE" --from-file="$SCRIPTPATH/../bin/spawn_test.py" -o yaml --dry-run=client | kubectl apply -f -

# Restart hub. The hub needs to actually restart to load the config changes,
# need to delete and recreate instead of just `kubectl apply`
kubectl delete -f "$SCRIPTPATH/../k8s-yaml/jupyterhub.yaml"
# Wait for stop
echo "Waiting to stop existing pod..."
while kubectl get pods -n "$NAMESPACE" | grep '^jupyterhub-.*Running' ; do
    sleep 1
done
kubectl create -f "$SCRIPTPATH/../k8s-yaml/jupyterhub.yaml"
