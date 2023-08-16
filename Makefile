JH_VERSION=4.0.1
VER=${JH_VERSION}-2023-08-16
IMAGE=harbor.cs.aalto.fi/jupyter-internal/jupyterhub-cs:${VER}

build:
	docker build -t ${IMAGE} --build-arg JH_VERSION=${JH_VERSION} .

push: build
	docker push ${IMAGE}
