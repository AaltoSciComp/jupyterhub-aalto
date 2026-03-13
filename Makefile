JH_VERSION=4.1.6
VER=${JH_VERSION}-2026-03-13
IMAGE=harbor.cs.aalto.fi/jupyter-internal/jupyterhub-cs:${VER}

build:
	docker build -t ${IMAGE} --build-arg JH_VERSION=${JH_VERSION} .

push: build
	docker push ${IMAGE}
