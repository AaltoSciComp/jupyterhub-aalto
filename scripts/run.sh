#!/usr/bin/bash
echo "Begin jupyterhub logs"
set -x
# shellcheck source=/dev/null
source /etc/localusers.sh        # k8s mounted secret
echo " \
130.233.251.4   dc01.org.aalto.fi \
130.233.251.5   dc02.org.aalto.fi \
130.233.251.6   dc03.org.aalto.fi \
130.233.251.7   dc04.org.aalto.fi \
" >> /etc/hosts
if [[ -z "${NO_AD_JOIN}" ]]; then
  join_ad.sh < /etc/adpw.txt   # k8s mounted secret
fi
service sssd start
tries=0
if [[ -z "${NO_AD_JOIN}" ]]; then
  while true;
  do
    if id darstr1 > /dev/null; then
      break;
    fi
    tries=$((tries+1));
    echo "Trying to connect to aalto ldap: $tries tries so far..."
    sleep 10;
  done
fi
jupyterhub
