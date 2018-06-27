cat /etc/adpw.txt | join_ad.sh
service sssd start
tries=0
while true;
do
  id murhum1
  if [ $? -eq 0 ]; then
    break;
  fi
  tries=$(($tries+1));
  echo "Trying to connect to aalto ldap: $tries tries so far..."
  sleep 10;
done
jupyterhub
