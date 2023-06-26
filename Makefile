JH_VERSION=1.4.2
VER=${JH_VERSION}-2023-07-18
IMAGE=harbor.cs.aalto.fi/jupyter-internal/jupyterhub-cs:${VER}

build:
	docker build -t ${IMAGE} --build-arg JH_VERSION=${JH_VERSION} .

push: build
	docker push ${IMAGE}
