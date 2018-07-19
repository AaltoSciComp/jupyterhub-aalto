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

RUN groupadd -r -g 1100 teststudent && adduser --uid 1100 --gid 1100 --quiet --disabled-password --shell /bin/bash --no-create-home --gecos "Test student,,," teststudent
RUN echo "teststudent:teststudent" | chpasswd

RUN groupadd -r -g 1101 testinstructor && adduser --uid 1101 --gid 1101 --quiet --disabled-password --shell /bin/bash --no-create-home --gecos "Test instructor,,," testinstructor
RUN echo "testinstructor:testinstructor" | chpasswd

RUN groupadd -r -g 1102 student1 && adduser --uid 1102 --gid 1102 --quiet --disabled-password --shell /bin/bash --no-create-home --gecos "Student 1,,," student1
RUN groupadd -r -g 1103 student2 && adduser --uid 1103 --gid 1103 --quiet --disabled-password --shell /bin/bash --no-create-home --gecos "Student 2,,," student2
RUN groupadd -r -g 1104 student3 && adduser --uid 1104 --gid 1104 --quiet --disabled-password --shell /bin/bash --no-create-home --gecos "Student 3,,," student3
RUN echo "student1:passwordA1" | chpasswd
RUN echo "student2:passwordA1" | chpasswd
RUN echo "student3:passwordA1" | chpasswd

CMD ["bash", "-c", "/run.sh"]
