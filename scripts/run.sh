echo "Begin jupyterhub logs"
set -x
source /etc/localusers.sh        # k8s mounted secret
cat /etc/adpw.txt | join_ad.sh   # k8s mounted secret
service sssd start
tries=0
while true;
do
  id darstr1
  if [ $? -eq 0 ]; then
    break;
  fi
  tries=$(($tries+1));
  echo "Trying to connect to aalto ldap: $tries tries so far..."
  sleep 10;
done
jupyterhub
