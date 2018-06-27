cat /etc/adpw.txt | join_ad.sh
service sssd start
tries=0
while [ ! id murhum1 && $tries < 10 ]; do
  tries = $(($tries+1));
  echo "Try $tries, sleeping..."
  sleep 10;
done
jupyterhub
