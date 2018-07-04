FROM jupyterhub/jupyterhub:0.9

# Install dependencies

# Jupyterhub & co
RUN pip install jupyter
RUN pip install pyyaml

# kube-spawner
RUN pip install https://github.com/jupyterhub/kubespawner/archive/cff7f01.tar.gz

# nbgrader & enable it
RUN pip install nbgrader
RUN jupyter nbextension install --sys-prefix --py nbgrader --overwrite
RUN jupyter nbextension enable --sys-prefix --py nbgrader
RUN jupyter serverextension enable --sys-prefix --py nbgrader

# Enable SSH stuff
COPY files/known_hosts /root/.ssh/known_hosts
COPY files/id_rsa_hub /root/.ssh/id_rsa
RUN chmod go-rwx /root/.ssh/*

# Enable aalto domain join
RUN apt-get update && apt-get install -y adcli sssd sssd-krb5 krb5-config sssd-ldap sssd-ad libpam-sss
COPY files/krb5.conf /etc/krb5.conf
COPY files/krb5.keytab /etc/krb5.keytab
COPY files/sssd.conf /etc/sssd/sssd.conf
RUN chmod 600 /etc/sssd/sssd.conf

COPY scripts/join_ad.sh /usr/local/bin/join_ad.sh
RUN chmod +x /usr/local/bin/join_ad.sh

COPY scripts/run.sh /run.sh
RUN chmod +x /run.sh

COPY cull_idle_servers.py /cull_idle_servers.py
RUN chmod +x /cull_idle_servers.py

RUN mkdir /courses

RUN adduser --quiet --disabled-password --shell /bin/bash --home /home/student --gecos "Test student" teststudent
RUN echo "teststudent:teststudent" | chpasswd

RUN adduser --quiet --disabled-password --shell /bin/bash --home /home/student --gecos "Test instructor" testinstructor
RUN echo "testinstructor:testinstructor" | chpasswd

CMD ["bash", "-c", "/run.sh"]
