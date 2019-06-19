# Aalto JupyterHub for light computing and teaching

This repository contains configuration for a JupyterHub deployment
using kubernetes.  This deployment is very integrated into existing
Aalto University systems, and thus extensive customization is probably
needed.

## Philosophy

* Kubernetes provides the underlying compute and infra.

* All users map to institution users: both usernames and UIDs.
  Institution groups are used to manage instructors for each course,
  `jupyter-$coursename`.

* All data is stored on institution-provided NFS under real UIDs.
  This means that all users can access their data on university shell
  servers and via direct mount to their laptops.

* Software provided via Docker images.  For the most part all images
  are identical and it contains anything that anyone may need.  All
  setup is in
  [jupyter-aalto-singleuser](https://github.com/AaltoScienceIT/jupyter-aalto-singleuser).

* Courses have shared directories which are mounted for instructors.
  An exchange directory is mounted for both instructors and students.

* [nbgrader](https://nbgrader.readthedocs.io/) is used for assignments
  for students.  But be aware that nbgrader is good at manipulating
  notebooks, it is *not* a learning management system, basically a
  fancy way to copy files.  This is facilitated via our common NFS
  mounts.

* Even though nbgrader is installed and the most common use, anyone
  may use these service for light computing for their own work.

* A directory of YAML files is used to manage courses.  JupyterHub's
  `pre_spawn_hook` is used to do all the course setup - for us, this
  is a very long, hackish function but does the job quite effectively
  and gives us a lot of flexibility.




## Using this repository.

* `*.yaml` is all the Kubernetes configuration.  Using `kubectl create
  -f` sets up things.

* `*.sh` are mostly scripts which manage kubernetes, it calls
  `kubectl` for you to set up things.  For example, `./remake-hub.sh`
  bounces the hub to update configuration.

* `jupyterhub_config.py` is where all of our local magic happens.

* There is a `secrets/` repository which is not public - this has some
  key files for creating test users, joining ActiveDirectory for PAM
  authentication, and so on.

* `scripts/` are various unsorted scripts.

Currently, actually using this is not really known.  You'd `kubectl
create -f` a bunch of stuff and then `./remake-*.sh` to start the hub
and other processes.  But there's probably a lot more magic in
there...



## See also

* "Zero to JupyterHub" is another JH, but despite the name it's
  Kubernetes-only.  It uses Helm charts to automate everything.  It
  operates as a stand-alone service (what we do here is far more
  integrated to university
  systems). https://zero-to-jupyterhub.readthedocs.io/en/latest/



## Contact

Richard Darst
[email](https://people.aalto.fi/index.html?language=english#richard_darst),
Aalto University
