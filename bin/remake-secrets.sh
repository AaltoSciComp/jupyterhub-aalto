kubectl delete secret -n jupyter tls
kubectl create secret -n jupyter tls tls --cert=secrets/jupyter_cs_aalto_fi.crt --key=secrets/jupyter.cs.aalto.fi.key

kubectl delete secret -n jupyter adpw.txt
kubectl create secret -n jupyter generic adpw.txt --from-file=secrets/adpw.txt

kubectl delete secret -n jupyter localusers
kubectl create secret -n jupyter generic localusers --from-file=secrets/localusers.sh

kubectl delete secret -n jupyter chp-secret
kubectl create secret -n jupyter generic chp-secret --from-file=secrets/chp-secret.txt

kubectl delete secret -n jupyter idrsa
kubectl create secret -n jupyter generic idrsa --from-file=secrets/id_rsa_hub
kubectl delete secret -n jupyter idrsapub
kubectl create secret -n jupyter generic idrsapub --from-file=secrets/id_rsa_hub.pub
kubectl delete secret -n jupyter knownhosts
kubectl create secret -n jupyter generic knownhosts --from-file=secrets/known_hosts

