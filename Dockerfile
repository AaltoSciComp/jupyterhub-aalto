FROM jupyterhub/jupyterhub:0.9

RUN pip install jupyter
RUN pip install https://github.com/jupyterhub/kubespawner/archive/cff7f01.tar.gz
RUN adduser --quiet --disabled-password --shell /bin/bash --home /home/test --gecos "Test" test
RUN echo "test:test" | chpasswd
