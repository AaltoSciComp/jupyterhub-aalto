kubectl delete secret tls
kubectl create secret tls tls --cert=secrets/jupyter_cs_aalto_fi.crt --key=secrets/jupyter.cs.aalto.fi.key

kubectl delete secret adpw.txt
kubectl create secret generic adpw.txt --from-file=secrets/adpw.txt

kubectl delete secret localusers
kubectl create secret generic localusers --from-file=secrets/localusers.sh

kubectl delete secret chp-secret
kubectl create secret generic chp-secret --from-file=secrets/chp-secret.txt

kubectl delete secret idrsa
kubectl create secret generic idrsa --from-file=secrets/id_rsa
kubectl delete secret idrsapub
kubectl create secret generic idrsapub --from-file=secrets/id_rsa.pub
kubectl delete secret knownhosts
kubectl create secret generic knownhosts --from-file=secrets/known_hosts

