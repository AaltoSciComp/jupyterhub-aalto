SCRIPTPATH="$( cd "$(dirname "$0")" ; pwd -P )"

kubectl create configmap jupyterhub-config --from-file=$SCRIPTPATH/jupyterhub_config.py
kubectl create secret generic adpw.txt --from-file=$SCRIPTPATH/adpw.txt
kubectl create -f $SCRIPTPATH/jupyterhub.yaml
