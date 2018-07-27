SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

$SCRIPTPATH/delete-hub.sh
# sometimes this proxy pid needs deletion... eventually find a better solution.
rm /mnt/jupyter/admin/hubdata/jupyterhub-proxy.pid
$SCRIPTPATH/create-hub.sh
