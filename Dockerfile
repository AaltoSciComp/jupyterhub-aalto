FROM jupyterhub/jupyterhub:0.9

# Install dependencies
RUN pip install jupyter
RUN pip install https://github.com/jupyterhub/kubespawner/archive/cff7f01.tar.gz

# Create /notebooks dir
RUN mkdir /notebooks
RUN chown 1000 /notebooks

COPY cull_idle_servers.py /cull_idle_servers.py
RUN chmod +x /cull_idle_servers.py

# Create test user
RUN adduser --quiet --disabled-password --shell /bin/bash --home /home/test --gecos "Test" test
RUN echo "test:test" | chpasswd
