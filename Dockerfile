FROM jupyterhub/jupyterhub:1.1.0b1

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends openssh-client vim && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Jupyterhub & co
RUN python3 -m pip install jupyter python-dateutil pytz pyyaml

# using a commit from Dec 27, 2019 instead of a release because there hasn't
# been a new release in a long time
RUN python3 -m pip install https://github.com/jupyterhub/kubespawner/archive/1b4539c.tar.gz

# Enable SSH stuff
COPY secrets/known_hosts /root/.ssh/known_hosts
COPY secrets/id_rsa_hub /root/.ssh/id_rsa
RUN chmod go-rwx /root/.ssh/*

# Enable aalto domain join
RUN apt-get update && apt-get install -y adcli sssd sssd-krb5 krb5-config sssd-ldap sssd-ad libpam-sss
COPY secrets/krb5.conf /etc/krb5.conf
COPY secrets/krb5.keytab.withkeys /etc/krb5.keytab
COPY secrets/sssd.conf /etc/sssd/sssd.conf
RUN chmod 600 /etc/sssd/sssd.conf /etc/krb5.keytab

COPY secrets/join_ad.sh /usr/local/bin/join_ad.sh
RUN chmod +x /usr/local/bin/join_ad.sh

COPY scripts/run.sh /run.sh
RUN chmod +x /run.sh

# These two copies are no longer needed - dynamically mounted in.
COPY scripts/cull_idle_servers.py /cull_idle_servers.py
COPY scripts/hub_status_service.py /hub_status_service.py
RUN chmod +x /cull_idle_servers.py /hub_status_service.py

RUN mkdir /courses

CMD ["bash", "-c", "/run.sh"]
