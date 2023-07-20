ARG JH_VERSION=1.4.2
FROM jupyterhub/jupyterhub:${JH_VERSION}
ARG JH_VERSION
ENV JH_VERSION=${JH_VERSION}

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends openssh-client vim && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Jupyterhub & co
#  PyJWT is for oauthenticator
RUN python3 -m pip install jupyter python-dateutil pytz pyyaml oauthenticator PyJWT
# Install latest to get newer features:
#RUN python3 -m pip install https://github.com/jupyterhub/jupyterhub/archive/f3c3225.tar.gz

# kubespawner
# List jupyterhub as a dependency to prevent pip from upgrading the package
RUN python3 -m pip install jupyterhub-kubespawner==4.3.0 jupyterhub==${JH_VERSION}

# Enable aalto domain join
RUN apt-get update && apt-get install -y adcli sssd sssd-krb5 krb5-config sssd-ldap sssd-ad libpam-sss
COPY --chmod=644 secrets/krb5.conf /etc/krb5.conf
# Ubuntu 22.04 has broken default flags for sssd
RUN sed -i 's/DAEMON_OPTS="-D -f"/DAEMON_OPTS="-D --logger=files"/' /etc/default/sssd

COPY secrets/join_ad.sh /usr/local/bin/join_ad.sh
RUN chmod +x /usr/local/bin/join_ad.sh

COPY scripts/run.sh /run.sh
RUN chmod +x /run.sh

RUN mkdir /courses

CMD ["bash", "-c", "/run.sh"]
