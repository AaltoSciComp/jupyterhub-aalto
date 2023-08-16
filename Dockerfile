ARG JH_VERSION=1.4.2
FROM jupyterhub/jupyterhub:${JH_VERSION}
ARG JH_VERSION
ENV JH_VERSION=${JH_VERSION}

# Install dependencies
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        openssh-client vim && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install -U --no-cache-dir \
        pip && \
    rm -rf /root/.cache/pip/*

# Jupyterhub & co
#  PyJWT is for oauthenticator
RUN python3 -m pip install --no-cache-dir \
        # TODO: Is this actually required? Most jupyter stuff should come from
        # upstream
        jupyter \
        # Used by cull_idle_servers and hub_status_service
        python-dateutil \
        pytz \
        # Added 2018-07-27, unknown use
        pyyaml \
        # https://oauthenticator.readthedocs.io/en/latest/reference/changelog.html
        'oauthenticator<7' \
        # Used by oauthenticator
        PyJWT \
        # Fix CVE-2023-37920
        'certifi>=2023.7.22' \
    && \
    rm -rf /root/.cache/pip/*

# kubespawner
# Listing jupyterhub here separately to prevent it from being unintentionally
# upgraded as a dependency
# https://jupyterhub-kubespawner.readthedocs.io/en/latest/changelog.html
RUN python3 -m pip install \
        jupyterhub-kubespawner==4.3.0 \
        jupyterhub==${JH_VERSION} \
    && \
    rm -rf /root/.cache/pip/*

# Enable aalto domain join
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        adcli sssd sssd-krb5 krb5-config sssd-ldap sssd-ad libpam-sss && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --chmod=644 secrets/krb5.conf /etc/krb5.conf
# Ubuntu 22.04 has broken default flags for sssd
RUN sed -i 's/DAEMON_OPTS="-D -f"/DAEMON_OPTS="-D --logger=files"/' /etc/default/sssd

COPY secrets/join_ad.sh /usr/local/bin/join_ad.sh
RUN chmod +x /usr/local/bin/join_ad.sh

COPY scripts/run.sh /run.sh
RUN chmod +x /run.sh

RUN mkdir /courses

CMD ["bash", "-c", "/run.sh"]
