SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

# Syntax check the hub config file first.
if ! python3 -m py_compile jupyterhub_config.py ; then
    echo "jupyterhub_config.py has invalid syntax, aborting the hub restart."
    exit
fi

$SCRIPTPATH/delete-hub.sh
# sometimes this proxy pid needs deletion... eventually find a better solution.
rm -f /mnt/jupyter/admin/hubdata/jupyterhub-proxy.pid
$SCRIPTPATH/create-hub.sh
