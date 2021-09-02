SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"
NAMESPACE=${1:-jupyter}
echo "Namespace: $NAMESPACE"

# Syntax check the hub config file first.
if ! python3 -m py_compile $SCRIPTPATH/../jupyterhub_config.py ; then
    echo "jupyterhub_config.py has invalid syntax, aborting the hub restart."
    exit
fi

$SCRIPTPATH/delete-hub.sh $NAMESPACE
# sometimes this proxy pid needs deletion... eventually find a better solution.
if [ "$NAMESPACE" = "jupyter" ]; then
    JUPYTER_PATH=/mnt/jupyter
elif [ "$NAMESPACE" = "jupyter-test" ]; then
    JUPYTER_PATH=/mnt/jupyter/jupyter-test
fi
rm -f $JUPYTER_PATH/admin/hubdata/jupyterhub-proxy.pid
mkdir -p $JUPYTER_PATH/software
mkdir -p $JUPYTER_PATH/shareddata

$SCRIPTPATH/create-hub.sh $NAMESPACE
