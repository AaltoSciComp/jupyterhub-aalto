#!/bin/bash
set -uo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
NAMESPACE=${1:-jupyter}
source "$SCRIPTPATH/_check_namespace.sh"

JMGR_HOSTNAME=root@jupyter-manager-2.cs.aalto.fi

# Syntax check the hub config file first.
if ! python3 -m py_compile $SCRIPTPATH/../jupyterhub_config.py ; then
    echo "jupyterhub_config.py has invalid syntax, aborting the hub restart."
    exit
fi

echo "Stopping hub"
$SCRIPTPATH/delete-hub.sh $NAMESPACE
# sometimes this proxy pid needs deletion... eventually find a better solution.
if [ "$NAMESPACE" = "jupyter" ]; then
    JUPYTER_PATH=/mnt/jupyter
elif [ "$NAMESPACE" = "jupyter-test" ]; then
    JUPYTER_PATH=/mnt/jupyter/jupyter-test
fi
echo "Running ssh"
timeout 2 ssh $JMGR_HOSTNAME "rm -f $JUPYTER_PATH/admin/hubdata/jupyterhub-proxy.pid"
timeout 2 ssh $JMGR_HOSTNAME "mkdir -p \
    $JUPYTER_PATH/software \
    $JUPYTER_PATH/shareddata \
    $JUPYTER_PATH/admin \
    && chmod o-rwx $JUPYTER_PATH/admin"

echo "Starting hub"
$SCRIPTPATH/create-hub.sh $NAMESPACE
