import copy
import glob
import grp
import os
import pwd # for resolving username --> uid
import re
import socket
import sys
import time
import yaml

c.Application.log_level = 'INFO'


# Basic JupyterHub config
#c.JupyterHub.bind_url = 'http://:8000'   # we have separate proxy now
c.JupyterHub.cleanup_servers = False
c.JupyterHub.hub_bind_url = 'http://0.0.0.0:8081'
c.JupyterHub.cleanup_servers = False  # leave servers running if hub restarts
c.JupyterHub.template_paths = ["/srv/jupyterhub/templates/"]
# Proxy config
#c.ConfigurableHTTPProxy.api_url = 'http://jupyterhub-chp-svc.default:8001'  # 10.104.184.140
c.ConfigurableHTTPProxy.api_url = 'http://%s:8001'%os.environ['JUPYTERHUB_CHP_SVC_SERVICE_HOST']
c.ConfigurableHTTPProxy.auth_token = open('/srv/jupyterhub/chp-secret.txt').read()
print('auth_token=', repr(c.ConfigurableHTTPProxy.auth_token), file=sys.stderr)
c.ConfigurableHTTPProxy.should_start = False


# Authenticator config
#c.Authenticator.delete_invalid_users = True  # delete users once no longer in Aalto AD
c.Authenticator.admin_users = {'darstr1', }


# Spawner config
c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'
c.KubeSpawner.start_timeout = 60 * 5
#c.KubeSpawner.hub_connect_ip = "jupyter-svc.default"
c.JupyterHub.hub_connect_ip = os.environ['JUPYTERHUB_SVC_SERVICE_HOST']
c.KubeSpawner.hub_connect_port = 8081
c.KubeSpawner.http_timeout = 60 * 5
c.KubeSpawner.disable_user_config = True
c.KubeSpawner.common_labels = { "app": "notebook-server" }
# Volume mounts
DEFAULT_VOLUMES = [
  {
    "name": "user",
    "nfs": {
      "server": "jhnas.org.aalto.fi",
      "path": "/vol/jupyter/u/{username}"
    }
  },
]
DEFAULT_VOLUME_MOUNTS = [
  { "mountPath": "/notebooks", "name": "user" },
]
c.KubeSpawner.volumes = DEFAULT_VOLUMES
c.KubeSpawner.volume_mounts = DEFAULT_VOLUME_MOUNTS



# Find all of our courses and profiles
COURSES = { }
COURSES_TS = None
METADIR = "/courses/meta"
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
    # First round: load raw data with users and so on.
    for course_file in glob.glob(os.path.join(METADIR, '*.yaml')):
        #print("X"*10, "course file", course_file, file=sys.stderr)
        course_slug = os.path.splitext(os.path.basename(course_file))[0]
        if course_slug.endswith('-users'):
            course_slug = course_slug[:-6]
        course_data = yaml.load(open(course_file))
        #print(course_slug, course_data, file=sys.stderr)
        if course_slug not in courses:
            courses[course_slug] = { }
        if 'instructors' in course_data: course_data['instructors'] = set(course_data['instructors'])
        if 'students'    in course_data: course_data['students']    = set(course_data['students'])
        courses[course_slug].update(course_data)
        #print(course_slug, course_data, file=sys.stderr)

    # Second round: make the data consistent, add GIDs, etc.
    for course_slug, course_data in courses.items():
        try:
            if 'gid' not in course_data:
                print(grp.getgrnam('jupyter-'+course_slug).gr_gid, file=sys.stderr)
                course_data['gid'] = grp.getgrnam('jupyter-'+course_slug).gr_gid
            #print(grp.getgrnam('jupyter-'+course_slug), file=sys.stderr)
            course_data['instructors'] |= set(grp.getgrnam('jupyter-'+course_slug).gr_mem)
        except KeyError:
            print("ERROR: group {} can not look up group info".format(course_slug), file=sys.stderr)
        #print(course_slug, course_data, file=sys.stderr)

    COURSES = courses
    return COURSES
GET_COURSES()

def get_profile_list(spawner):
    #c.JupyterHub.log.debug("Recreating profile list")
    PROFILE_LIST = [
        {'display_name': 'General use + JupyterLab',
         'default': True,
         'kubespawner_override': {
             # if callable is here, set spawner.k = v(spawner)
             'course_slug': '',
             'default_url': "lab/tree/notebooks",
         }
        }
    ]
    PROFILE_LIST.append(copy.deepcopy(PROFILE_LIST[0]))
    PROFILE_LIST[-1]['display_name'] = 'General use'
    del PROFILE_LIST[-1]['default']
    del PROFILE_LIST[-1]['kubespawner_override']['default_url']
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


# User environment config
c.KubeSpawner.image_spec = 'aaltoscienceit/notebook-server:0.3.3'
c.KubeSpawner.default_url = "tree/notebooks"
c.KubeSpawner.notebook_dir = "/"
# doesn't work, because we start as root, this happens as root but we
# have root_squash.
#c.KubeSpawner.singleuser_working_dir = '/notebooks'
# Note: instructors get different limits, see below.
c.KubeSpawner.cpu_limit = 1
c.KubeSpawner.mem_limit = '512M'
c.KubeSpawner.cpu_guarantee = .2
c.KubeSpawner.mem_guarantee = '256M'


def create_user_dir(username, uid):
    os.system('ssh jupyter-k8s-admin.cs.aalto.fi "/root/jupyterhub/scripts/create_user_dir.sh {0} {1}"'.format(username, uid))


def pre_spawn_hook(spawner):
    # Get basic info
    username = spawner.user.name
    userinfo = pwd.getpwnam(username)
    homedir = userinfo.pw_dir
    if homedir.startswith('/u/'): homedir = homedir[3:]
    uid = userinfo.pw_uid
    spawner.log.debug("pre_spawn_hook: %s running %s", username, getattr(spawner, 'course_slug', ''))

    # Set basic spawner properties
    #storage_capacity = ???
    spawner.environment = environ = { }  # override env
    cmds = [ "source start-notebook.sh" ]  # args added later in KubeSpawner
    # Remove the .jupyter config that is already there
    #cmds.insert(-1, "echo 'umask 0007' >> /home/jovyan/.bashrc")
    #cmds.insert(-1, "echo 'umask 0007' >> /home/jovyan/.profile")
    #cmds.insert(-1, "pip install --upgrade --no-deps https://github.com/rkdarst/nbgrader/archive/live.zip")

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
        environ['NB_GROUP'] = 'domain-users'
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
    cmds.insert(-1, r'echo "if [ \"\$SHLVL\" = 1 -a \( \"\$PWD\" = \"\$HOME\" -o \"\$PWD\" = / \)  ] ; then cd /notebooks ; fi" >> /home/jovyan/.bashrc')

    #for line in ['[user]',
    #             '    name = {}'.format(fullname),
    #             '    email = {}'.format(email),
    #             ]:
    #    cmds.insert(-1, r"echo '{}' >> /home/jovyan/.gitconfig".format(line))
    #    cmds.insert(-1, "fix-permissions /home/jovyan/.gitconfig")

    course_slug = spawner.course_slug
    # We are not part of a course, so do only generic stuff
    if not course_slug:
        cmds.insert(-1, "disable_formgrader.sh")

    # Course configuration - only if it is a course
    else:
        spawner.log.info("pre_spawn_hook: course %s", course_slug)
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
        exchange_readonly = (course_data.get('restrict_submit', False) and 'username' not in course_data.get('students', {})
                                                                       and 'username' not in course_data.get('instructors', {}))
        spawner.volume_mounts.append({"mountPath": "/srv/nbgrader/exchange",
                                      "name": "exchange",
                                      "readOnly": exchange_readonly})
        # Add course shared data, if it exists
        if os.path.exists("/coursedata/{}".format(course_slug)):
            spawner.volumes.append({
                "name": "coursedata",
                "nfs": {
                    "server": "jhnas.org.aalto.fi",
                    "path": "/vol/jupyter/course/coursedata/{}".format(course_slug)
                }
            })
            spawner.volume_mounts.append({"mountPath": "/coursedata",
                                          "name": "coursedata",
                                          "readOnly": username not in course_data.get('instructors', {})})


        # Jupyter/nbgrader config
        for line in ['c = get_config()',
                     'c.CourseDirectory.root = "/course"',
                     'c.Exchange.course_id = "{}"'.format(course_slug),
                     'c.Exchange.multiuser = True',
                     'c.Exchange.groupshared = True',
                     'c.BaseConverter.groupshared = True',
                     'c.Exchange.assignment_dir = "/notebooks/"',
                     'c.AssignmentList.assignment_dir = "/notebooks/"',
                     ]:
            cmds.insert(-1, r"echo '{}' >> /etc/jupyter/nbgrader_config.py".format(line))
        for line in ['c.AssignmentList.assignment_dir = "/notebooks/"',
                     ]:
            cmds.insert(-1, r"echo '{}' >> /etc/jupyter/jupyter_notebook_config.py".format(line))

        # Instructors
        allow_spawn = False
        if username in course_data.get('instructors', {}):
            spawner.log.info("pre_spawn_hook: User %s is an instructor for %s", username, course_slug)
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
            if 'gid' in course_data:
                course_gid = int(course_data['gid'])
            spawner.log.debug("pre_spawn_hook: Course gid for {} is {}", course_slug, course_gid)
            cmds.insert(-1, r"umask 0007")  # also used through sudo
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
                cmds.insert(-1, r"sed -r -i 's/^(UMASK.*)022/\1007/' /etc/login.defs")
                cmds.insert(-1, r"echo Defaults umask=0007, umask_override >> /etc/sudoers")
                #cmds.insert(-1, r"{{ test ! -e /course/gradebook.db && sudo -u nobody touch /course/gradebook.db && chown {} /course/gradebook.db && chmod 660 /course/gradebook.db ; true ; }}".format(username))  # {{ and }} escape .format()
                environ['NB_PRE_START_HOOK'] =  r"set -x ; sudo -u {username} bash -c 'set -x ; test ! -e /course/gradebook.db && touch /course/gradebook.db && chmod 660 /course/gradebook.db || true ;'".format(username=username)  # {{ and }} escape .format()
            else:
                spawner.gid = spawner.fs_gid = course_gid
                spawner.supplemental_gids.insert(0, course_gid)
                cmds.insert(-1, r"test ! -e /course/gradebook.db && touch /course/gradebook.db && chmod 660 /course/gradebook.db || true")
                # umask 0007 inserted above
        else:
            cmds.insert(-1, "disable_formgrader.sh")

        # Student config
        if username in course_data.get('students', {}):
            spawner.log.info("pre_spawn_hook: User %s is a student for %s", username, course_slug)
            allow_spawn = True

        if not allow_spawn and course_data.get('private', False):
            spawner.log.info("pre_spawn_hook: User %s is blocked spawning %s", username, course_slug)
            raise RuntimeError("You ({}) are not allowed to use the {} environment.  Please contact the course instructors".format(username, course_slug))

    # User- and course-specific hooks
    hook_file = '/srv/jupyterhub/hooks-user/{}.py'.format(username)
    if os.path.exists(hook_file):
        spawner.log.info("pre_spawn_hook: Running %s", hook_file)
        exec(open(hook_file).read())
    hook_file = '/srv/jupyterhub/hooks-course/{}.py'.format(course_slug)
    if course_slug and os.path.exists(hook_file):
        spawner.log.info("pre_spawn_hook: Running %s", hook_file)
        exec(open(hook_file).read())

    # Common final setup
    #print(vars(spawner))
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

