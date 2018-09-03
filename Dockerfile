FROM jupyterhub/jupyterhub:0.9.1

# Install dependencies

# Jupyterhub & co
RUN pip install jupyter
RUN pip install pyyaml

# kube-spawner
RUN pip install https://github.com/jupyterhub/kubespawner/archive/27056a7.tar.gz

# nbgrader & enable it
RUN pip install git+https://github.com/rkdarst/nbgrader@live
RUN jupyter nbextension install --sys-prefix --py nbgrader --overwrite
RUN jupyter nbextension enable --sys-prefix --py nbgrader
RUN jupyter serverextension enable --sys-prefix --py nbgrader

# Enable SSH stuff
COPY secrets/known_hosts /root/.ssh/known_hosts
COPY secrets/id_rsa_hub /root/.ssh/id_rsa
RUN chmod go-rwx /root/.ssh/*

# Enable aalto domain join
RUN apt-get update && apt-get install -y adcli sssd sssd-krb5 krb5-config sssd-ldap sssd-ad libpam-sss
COPY secrets/krb5.conf /etc/krb5.conf
COPY secrets/krb5.keytab /etc/krb5.keytab
COPY secrets/sssd.conf /etc/sssd/sssd.conf
RUN chmod 600 /etc/sssd/sssd.conf

COPY scripts/join_ad.sh /usr/local/bin/join_ad.sh
RUN chmod +x /usr/local/bin/join_ad.sh

COPY scripts/run.sh /run.sh
RUN chmod +x /run.sh

COPY scripts/cull_idle_servers.py /cull_idle_servers.py
COPY scripts/hub_status_service.py /hub_status_service.py
RUN chmod +x /cull_idle_servers.py

RUN mkdir /courses

CMD ["bash", "-c", "/run.sh"]
