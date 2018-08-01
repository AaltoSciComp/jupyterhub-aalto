kubectl delete secret tls
kubectl create secret tls tls --cert=secrets/jupyter_cs_aalto_fi.crt --key=secrets/jupyter.cs.aalto.fi.key

kubectl delete secret adpw.txt
kubectl create secret generic adpw.txt --from-file=secrets/adpw.txt

kubectl delete secret localusers
kubectl create secret generic localusers --from-file=secrets/localusers.sh
