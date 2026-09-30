# Aalto JupyterHub for light computing and teaching

This repository contains configuration for a JupyterHub deployment
using kubernetes.  This deployment is very integrated into existing
Aalto University systems, and thus extensive customization is probably
needed.

## Philosophy

* We do not provide services to courses, we provide accessible
  computing to users, with some add-ons for courses.  This means that
  users have full control of their data (it can benefit them beyond
  one course), but also more responsibility for the user.  We consider
  this good and a gentle step to learn to be independent.

* Courses exist as a hook which mounts course-specific shared
  directories.  A instructor files directory is mounted for
  instructors.  An exchange directory is mounted for both instructors
  and students.  nbgrader provides a way for the exchange to be used
  to send files to and from instructors, but nbgrader is *not* a
  learning management system and is *not* currently integrated to
  Aalto LMSs.  But it could be, and we are discussing this.

* Kubernetes provides the underlying management and compute.

* All users map to institution users: both usernames and UIDs.
  Institution groups are used to manage instructors for each course,
  the group `jupyter-$coursename` contains instructors for the course.

* All data is stored on institution-provided NFS under real UIDs.
  This means that all users can access their data on university shell
  servers and via direct mount to their laptops.

* Software provided via Docker images.  For the most part all images
  are identical and it contains anything that anyone may need.  All
  setup is in
  [jupyter-aalto-singleuser](https://github.com/AaltoScienceIT/jupyter-aalto-singleuser).

* [nbgrader](https://nbgrader.readthedocs.io/) is used for assignments
  for students.  But be aware that nbgrader is good at manipulating
  notebooks, it is *not* a learning management system, it is basically
  a fancy way to filter and copy files.  This is facilitated via our
  common NFS mounts.  Nbgrader does not some things expected from an
  LMS, such as immediate autograde and feedback.

* Even though nbgrader is installed and the most common use, anyone
  may use these service for light computing for their own work.

* A directory of YAML files is used to manage courses.  JupyterHub's
  `pre_spawn_hook` is used to do all the course setup - for us, this
  is a very long, hackish function but does the job quite effectively
  and gives us a lot of flexibility.

## Using this repository

* `k8s-yaml/*.yaml` is all the Kubernetes configuration.  Use `kubectl
  create -f` to set up things.

* `bin/` is mostly scripts which manage kubernetes, which calls
  `kubectl` to perform some common tasks.  For example,
  `./bin/remake-hub.sh` bounces the hub to update configuration.  You
  often need to go beyond what the scripts provide.

* `jupyterhub_config.py` is where all of our local magic happens.

* There is a `secrets/` repository which is not public - this has some
  key files for creating test users, joining ActiveDirectory for PAM
  authentication, and so on.  It must be cloned into `./secrets/`

* `scripts/` are generally scripts that are placed on the hub and not
  used directly.

## nbgrader question randomization

This deployment supports deterministic per-student randomization for
nbgrader assignments by using a question bank in a source notebook.

Enable in course YAML (`meta/*.yaml`) with:

```yaml
nbgrader_randomisation:
  enabled: true
  assignment: assign1
  pick_count: 3
  group_pick_counts:
    algebra: 2
    geometry: 1
  # Optional overrides:
  # source_notebook: /courses/{coursedir_slug}/files/source/assign1/assign1.ipynb
  # output_dir: /courses/{coursedir_slug}/files/randomized
  # question_metadata_key: aalto_nbgrader_bank
  # weight_key: weight
  # seed_salt: gausproc2026
```

Question-bank cells are identified by per-cell metadata. Cells without
the bank metadata are included for everyone; tagged question cells are
sampled with weighted sampling without replacement.
`pick_count` applies to questions without a group, while each entry in
`group_pick_counts` applies independently to the matching group.

Example cell metadata:

```json
{
  "aalto_nbgrader_bank": {
    "question_id": "q05",
    "group": "algebra",
    "weight": 1.0
  }
}
```

The generator is `scripts/nbgrader_randomize_release.py`. It runs when
an instructor spawns a course where randomization is enabled and writes
deterministic per-student notebooks and a manifest under the configured
output directory.

Fetching is integrated through a custom exchange plugin
`scripts/nbgrader_randomized_fetch.py` that is set as
`ExchangeFactory.fetch_assignment` for randomized courses. Students still
run standard `nbgrader fetch` / `nbgrader fetch_assignment`, but the fetched
notebook is replaced with that student's deterministic randomized variant.

* `course-mgmt/` are course management scripts used by admins.

* `user-scripts/` are scripts which users/instructors need to use
  (should be moved elsewhere).

Beyond the above, there is not really many instructions for using
this.  You'd `kubectl create -f` a bunch of stuff and then
`./bin/remake-*.sh` to start the hub and other processes.  But there's
probably a lot more magic in there....  There is also plenty of
Aalto-specific configuration embedded in here.  We would be happy to
help factor this out.

## See also

* "Zero to JupyterHub" is another JH, but despite the name it's
  Kubernetes-only.  It uses Helm charts to automate everything.  It
  operates as a stand-alone service (what we do here is far more
  integrated to university
  systems). <https://zero-to-jupyterhub.readthedocs.io/en/latest/>

## Contact

Richard Darst
[email](https://people.aalto.fi/index.html?language=english#richard_darst),
Aalto University
