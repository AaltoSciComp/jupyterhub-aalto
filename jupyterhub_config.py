import glob
import os
import pwd # for resolving username --> uid
import re
import socket
import sys
import time
import yaml

c.Application.log_level = 'DEBUG'

# Basic JupyterHub config
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000
c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'
c.JupyterHub.cleanup_servers = False
c.JupyterHub.hub_ip = '0.0.0.0'
c.JupyterHub.hub_port = 8081
# Find our IP
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
host_ip = s.getsockname()[0]
s.close()
c.Authenticator.admin_users = {'darstr1', 'murhum1'}
c.JupyterHub.cleanup_servers = False  # leave servers running if hub restarts
c.JupyterHub.template_paths = ["/srv/jupyterhub/templates/"]

# Authenticator config

#c.JupyterHub.authenticator_class = 'jhub_remote_user_authenticator.remote_user_auth.RemoteUserAuthenticator'

#def add_user(self, user):
#    print("Adding user: user {} being added".format(user))
#    os.system('ssh jupyter-k8s-admin.cs.aalto.fi "hostname ; echo adding user {} ; /root/jupyterhub/scripts/adduser.py"'.format(user))
#c.Authenticator.add_user = add_user

# If whitelist undefined, any user can login
c.Authenticator.whitelist = set()

# Add usernames to whitelist - /courses is in k8s-jupyter-admin:/srv/courses
COURSES = { }
COURSES_TS = None
METADIR = "/courses/meta"
#for course_yaml in glob.glob(os.path.join(METADIR, '*.yaml')):
#    course_data = yaml.load(open(course_yaml))
#    course_slug = os.path.splitext(os.path.basename(course_yaml))[0]
#    COURSES[course_slug] = course_data
#    print(course_data)
#    for username in course_data.get('students', []):
#      c.Authenticator.whitelist.add(username)
#    for username in course_data.get('instructors', []):
#      c.Authenticator.whitelist.add(username)
def GET_COURSES():
    """Update the global COURSES dictionary.

    Wrapped in a function so that we can update even while the process
    is running.  Has some basic caching, so that we do not constantly
    regenerate this data.

    """
    global COURSES, COURSES_TS
    # Cache, don't unconditionally reload every time.
    # Regenerate if Check if we must regenerate data
    if COURSES_TS and COURSES_TS > time.time() - 10:
        return COURSES
    latest_yaml_ts = max(os.stat(course_file).st_mtime
                         for course_file in glob.glob(os.path.join(METADIR, '*.yaml')))
    if COURSES_TS and COURSES_TS > latest_yaml_ts:
        return COURSES
    COURSES_TS = time.time()
    #c.JupyterHub.log.debug("Re-generating course data")
    courses = { }
    for course_file in glob.glob(os.path.join(METADIR, '*.yaml')):
        course_slug = os.path.splitext(os.path.basename(course_file))[0]
        if course_slug.endswith('-users'):
            course_slug = course_slug[:-6]
        course_data = yaml.load(open(course_file))
        if course_slug not in courses:
            courses[course_slug] = { }
        courses[course_slug].update(course_data)
        #for username in course_data.get('students', []):
        #    c.Authenticator.whitelist.add(username)
        #for username in course_data.get('instructors', []):
        #    c.Authenticator.whitelist.add(username)
    COURSES = courses
    return COURSES
GET_COURSES()


# Spawner config
c.KubeSpawner.start_timeout = 60 * 5
c.KubeSpawner.image_spec = 'aaltoscienceit/notebook-server:0.2.6'
c.KubeSpawner.hub_connect_ip = host_ip
c.JupyterHub.hub_connect_ip = c.KubeSpawner.hub_connect_ip
c.KubeSpawner.hub_connect_port = 80
c.KubeSpawner.http_timeout = 60 * 5
c.KubeSpawner.disable_user_config = True
c.KubeSpawner.default_url = "tree/notebooks"
c.KubeSpawner.notebook_dir = "/"

# Volume mounts
DEFAULT_VOLUMES = [
  {
    "name": "user",
    "nfs": {
      "server": "jhnas.org.aalto.fi",
      "path": "/vol/jupyter/u/{username}"
    }
  },
  #{
  #  "name": "exchange",
  #  "nfs": {
  #    "server": "jhnas.org.aalto.fi",
  #    "path": "/vol/jupyter/exchange"
  #  }
  #},
  #{
  #  "name": "course",
  #  "nfs": {
  #    "server": "jhnas.org.aalto.fi",
  #    "path": "/vol/jupyter/course"
  #  }
  #}
]
DEFAULT_VOLUME_MOUNTS = [
  { "mountPath": "/notebooks", "name": "user" },
  #{ "mountPath": "/home/{username}", "name": "user" },
  #{ "mountPath": "/exchange", "name": "exchange" }
]
c.KubeSpawner.volumes = DEFAULT_VOLUMES
c.KubeSpawner.volume_mounts = DEFAULT_VOLUME_MOUNTS

# doesn't work, because we start as root, this happens as root but we
# have root_squash.
#c.KubeSpawner.singleuser_working_dir = '/notebooks'

# Note: instructors get different limits, see below.
c.KubeSpawner.cpu_limit = 1
c.KubeSpawner.mem_limit = '512M'
c.KubeSpawner.cpu_guarantee = .2
c.KubeSpawner.mem_guarantee = '256M'

def get_profile_list(spawner):
    #c.JupyterHub.log.debug("Recreating profile list")
    PROFILE_LIST = [
        {'display_name': 'Generic (for anyone to use)',
         'default': True,
         'kubespawner_override': {
             # if callable is here, set spawner.k = v(spawner)
             'course_slug': '',
         }
        }
    ]
    PROFILE_LIST.extend([{
        'display_name': course_data.get('name', course_slug),
        'kubespawner_override': {
            'course_slug': course_slug,}
        } for (course_slug, course_data) in GET_COURSES().items()
          if course_data.get('active', True) #and (not course_data.get('private', False)  # requires next kubespawner
                                             #     or spawner.user.name in course_data['instructors']
                                             #     or spawner.user.name in course_data['instructors'])
    ])
    return PROFILE_LIST
# In next version of kubespawner, leave as callable to regen every
# time, without restart.
c.KubeSpawner.profile_list = get_profile_list(None)
#if len(c.KubeSpawner.profile_list) < 2:
#    raise RuntimeError("Startup error: no course profiles found")



def create_user_dir(username, uid):
    os.system('ssh jupyter-k8s-admin.cs.aalto.fi "/root/jupyterhub/scripts/create_user_dir.sh {0} {1}"'.format(username, uid))



# profile_list --> use this instead of ProfileSpawner ?
def pre_spawn_hook(spawner):
    # Get basic info
    username = spawner.user.name
    userinfo = pwd.getpwnam(username)
    homedir = userinfo.pw_dir
    if homedir.startswith('/u/'): homedir = homedir[3:]
    uid = userinfo.pw_uid
    spawner.log.debug("Running pre-spawn hook for {}".format(username))

    # Set basic spawner properties
    #storage_capacity = ???
    spawner.environment = environ = { }  # override env
    cmds = [ "source start-notebook.sh" ]  # args added later in KubeSpawner
    # Remove the .jupyter config that is already there
    cmds.insert(-1, "echo 'umask 0007' >> /home/jovyan/.bashrc")
    cmds.insert(-1, "echo 'umask 0007' >> /home/jovyan/.profile")
    #cmds.insert(-1, "pip install --upgrade --no-deps https://github.com/rkdarst/nbgrader/archive/live.zip")
    # Fixed in latest base-notebook image.  Remove later:
    environ["XDG_CACHE_HOME"] = "/home/{}/.cache/".format(username)

    if uid < 1000: raise ValueError("uid can not be less than 1000 (is {})"%uid)
    c.KubeSpawner.working_dir = '/'

    # Note: current (summer 2018) conda version of kubespawner does
    # not use "uid" or "gid" options as you see in the latest
    # kubespawner.

    # Default setup of /etc/passwd: jovyan:x:1000:0
    # Default setup of /etc/group: users:x:100

    if 0:
        # Manually run as uid from outside the container
        spawner.singleuser_uid = uid
        # default of user in docker image (note: not in image kubespawer yet!)
        spawner.gid = spawner.fs_gid = 70000
        # group 'users' required in order to write config files etc
        spawner.supplemental_gids = [70000, 100]
    else:
        # To do this, you should have /home/$username exist...
        environ['NB_USER'] = username
        environ['NB_UID'] = str(uid)
        environ['NB_GID'] = '70000'
        #environ['GRANT_SUDO'] = 'yes'
        # The default jupyter image will use root access in order to su to the user as defined above.
        spawner.singleuser_uid = 0
        # Fix permissions.  Uses NB_GID only, and should not run on any NFS filesystems!
        #cmds.insert(-1, "fix-permissions /home/jovyan")
        #cmds.insert(-1, "fix-permissions $CONDA_DIR")

        # add default user to group 100 for file access. (Required
        # because sudo prevents supplemental_gids from taking effect
        # after the sudo).  The "jovyan" user is renamed to $NB_USER
        # on startup.
        #cmds.insert(-1, "adduser jovyan users")

    create_user_dir(username, uid) # TODO: Define path / server / type in yaml?
    #cmds.insert(-1, r'echo "if [ \"\$SHLVL\" = 1 -a \"\$PWD\" = \"\$HOME\" ] ; then cd /notebooks ; fi" >> /home/jovyan/.profile')
    cmds.insert(-1, r'echo "if [ \"\$SHLVL\" = 1 -a \"\$PWD\" = \"\$HOME\" ] ; then cd /notebooks ; fi" >> /home/jovyan/.bashrc')

    course_slug = spawner.course_slug
    # We are not part of a course, so do only generic stuff
    if not course_slug:
        cmds.insert(-1, "disable_formgrader.sh")

    # Course configuration - only if it is a course
    else:
        spawner.log.info("Pre-spawn hook for course=%s", course_slug)
        course_data = GET_COURSES()[course_slug]
        #filename = "/courses/{}.yaml".format(course_slug)
        #course_data = yaml.load(open(filename))
        if 'image' in course_data:
            spawner.image_spec = course_data['image']
        spawner.pod_name = 'jupyter-{}-{}{}'.format(username, course_slug, '-'+spawner.name if spawner.name else '')

        # Make a copy of the *default* class volumes.  The "spawner" object
        # is constantly reused.
        spawner.volumes = list(DEFAULT_VOLUMES)
        spawner.volume_mounts = list(DEFAULT_VOLUME_MOUNTS)

        # Add course exchange
        spawner.volumes.append({
            "name": "exchange",
            "nfs": {
                "server": "jhnas.org.aalto.fi",
                "path": "/vol/jupyter/exchange/{}".format(course_slug)
            }
        })
        # /srv/nbgrader/exchange is the default path
        spawner.volume_mounts.append({ "mountPath": "/srv/nbgrader/exchange", "name": "exchange" })
        # Add course shared data, if it exists
        if os.path.exists("/coursedata/{}".format(course_slug)):
            spawner.volumes.append({
                "name": "coursedata",
                "nfs": {
                    "server": "jhnas.org.aalto.fi",
                    "path": "/vol/jupyter/coursedata/{}".format(course_slug)
                }
            })
            spawner.volume_mounts.append({ "mountPath": "/coursedata", "name": "coursedata", "readOnly": True })


        # Jupyter/nbgrader config
        for line in ['c = get_config()',
                     'c.CourseDirectory.root = "/course"',
                     'c.Exchange.course_id = "{}"'.format(course_slug),
                     'c.Exchange.multiuser = True',
                     ]:
            cmds.insert(-1, r"echo '{}' >> /etc/jupyter/nbgrader_config.py".format(line))

        # Instructors
        allow_spawn = False
        if username in course_data.get('instructors', {}):
            allow_spawn = True
            # Instructors get the whole filesystem tree, because they
            # need to be able to access "/course", too.  Warning, you
            # will have different paths!  (fix later...)
            spawner.cpu_limit = 1
            spawner.mem_limit = '2048M'
            spawner.cpu_guarantee = .5
            spawner.mem_guarantee = '512M'
            for line in ['c.NbGrader.logfile = "/course/.nbgraber.log"',
                        ]:
                cmds.insert(-1, r"echo '{}' >> /etc/jupyter/nbgrader_config.py".format(line))
            if 'image_instructor' in course_data:
                spawner.image_spec = course_data['image_instructor']
            spawner.volumes.append({
                "name": "course",
                "nfs": {
                    "server": "jhnas.org.aalto.fi",
                    "path": "/vol/jupyter/course/{}".format(course_slug)
                }
            })
            spawner.volume_mounts.append({ "mountPath": "/course", "name": "course" })
            course_gid = os.stat('/courses/{}'.format(course_slug)).st_gid
            spawner.log.debug("Course gid for {} is {}".format(course_slug, course_gid))
            if 'NB_UID' in environ:
                # This branch happens only if we are root (see above)
                environ['NB_GID'] = str(course_gid)
                environ['NB_GROUP'] = 'jupyter-'+course_slug
                # The start.sh script renumbers the default group 100 to $NB_GID.  We rename it first.
                #cmds.insert(-1, "groupmod -n {} users".format('jupyter-'+course_slug))
                # We *need* to be in group 100, because a lot of the
                # default files (conda, etc) are group=rw=100.  We add
                # a *duplicate* group 100, and only the first one is
                # renamed in the image (in the jupyter start.sh)
                #cmds.insert(-1, "groupadd --gid 100 --non-unique users")
                #cmds.insert(-1, "adduser jovyan users")
            else:
                spawner.gid = spawner.fs_gid = course_gid
                spawner.supplemental_gids.insert(0, course_gid)
        else:
            cmds.insert(-1, "disable_formgrader.sh")

        # Student config
        if username in course_data.get('students', {}):
            allow_spawn = True

        if not allow_spawn and course_data.get('private', False):
            raise RuntimeError("You ({}) are not allowed to use the {} environment".format(username, course_slug))

    print(vars(spawner))
    # Common final setup
    spawner.cmd = ["bash", "-x", "-c", ] + [" && ".join(cmds)]

    
c.KubeSpawner.pre_spawn_hook = pre_spawn_hook

# Culler service
c.JupyterHub.services = [
  {
    'name': 'cull-idle',
    'admin': True,
    'command': 'python3 /cull_idle_servers.py --timeout=3600 --max-age=14400 --cull_every=300'.split(),
  },
  # Remove users from the DB every so often (1 month)... this has no practical effect.
  {
    'name': 'cull-inactive-users',
    'admin': True,
    'command': 'python3 /cull_idle_servers.py --cull-users --timeout=2678400 --cull-every=86400'.split(),
  }
]

