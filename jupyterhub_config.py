import glob
import socket
import os
import pwd # for resolving username --> uid
import yaml

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
METADIR = "/courses/meta"
for course_yaml in glob.glob(os.path.join(METADIR, '*.yaml')):
    course_data = yaml.load(open(course_yaml))
    course_slug = os.path.splitext(os.path.basename(course_yaml))[0]
    COURSES[course_slug] = course_data
    print(course_data)
    for username in course_data.get('students', []):
      c.Authenticator.whitelist.add(username)
    for username in course_data.get('instructors', []):
      c.Authenticator.whitelist.add(username)

# Spawner config
c.KubeSpawner.start_timeout = 60 * 5
c.KubeSpawner.singleuser_image_spec = 'fissio/notebook-server:0.1.4'
c.KubeSpawner.hub_connect_ip = host_ip
c.JupyterHub.hub_connect_ip = c.KubeSpawner.hub_connect_ip
c.KubeSpawner.hub_connect_port = 80
c.KubeSpawner.http_timeout = 60 * 5
c.KubeSpawner.disable_user_config = True

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

# doesn't work with root, do in startup script
c.KubeSpawner.singleuser_working_dir = '/notebooks'


def get_profile_list(spawner):
    PROFILE_LIST = [
        {'display_name': 'Generic (for anyone to use)',
         'default': True,
         'kubespawner_override': {
             # if callable is here, set spawner.k = v(spawner)
             #'image_spec': 'training/python:label',
             #'cpu_limit': 1,
             #'mem_limit': '512M',
             'course_slug': '',
         }
        }
    ]
    PROFILE_LIST.extend([{
        'display_name': course_data.get('name', course_slug),
        'kubespawner_override': {
            # if callable is here, set spawner.k = v(spawner)
            #'image_spec': 'training/python:label',
            #'cpu_limit': 1,
            #'mem_limit': '512M',
            'course_slug': course_slug,}
        } for (course_slug, course_data) in COURSES.items() if course_data.get('active', True)])
    return PROFILE_LIST
c.KubeSpawner.profile_list = get_profile_list(None)  # leave as callable to regen every time, without restart.
if len(c.KubeSpawner.profile_list) < 2:
    raise RuntimeError("Startup error: no course profiles found")



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

    # Set basic spawner properties
    spawner.singleuser_supplemental_gids = [100] # group 'users' required in order to write config files etc
    #self.gid = xxx
    #storage_capacity = ???
    spawner.environment = environ = { }  # override env
    print(spawner.cmd)
    cmds = [ "start-notebook.sh --notebook-dir=/notebooks" ]

    if uid < 1000: raise ValueError("uid can not be less than 1000 (is {})"%uid)
    c.KubeSpawner.working_dir = '/'

    if 0:
        # Manually run as uid from outside the container
        spawner.singleuser_uid = uid
        #cmds.insert(0, "adduser --uid {} --gid=70000 --no-create-home " # --home=/user
        #               "--disabled-password --disabled-login  {}".format(uid, username))
    else:
        # To do this, you should have /home/$username exist...
        environ['NB_USER'] = username
        environ['NB_UID'] = str(uid)
        environ['NB_GID'] = '70000'
        #environ['GRANT_SUDO'] = 'yes'
        # The default jupyter image will use root access in order to su to the user as defined above.
        spawner.singleuser_uid = 0

    create_user_dir(username, uid) # TODO: Define path / server / type in yaml?

    course_slug = spawner.course_slug
    # We are not part of a course, so do only generic stuff
    if not course_slug:
        cmds.insert(0, "disable_formgrader.sh")

    # Course configuration - only if it is a course
    else:
        course_data = COURSES[course_slug]
        #self.name = course_slug   # causes this to be added to pod name
        #filename = "/courses/{}.yaml".format(course_slug)
        #course_data = yaml.load(open(filename))

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
        spawner.volume_mounts.append({ "mountPath": "/exchange", "name": "exchange" })


        # Instructors
        allow_spawn = False
        if username in course_data.get('instructors', {}):
            allow_spawn = True
            spawner.volumes.append({
                "name": "course",
                "nfs": {
                    "server": "jhnas.org.aalto.fi",
                    "path": "/vol/jupyter/course/{}".format(course_slug)
                }
            })
            spawner.volume_mounts.append({ "mountPath": "/course", "name": "course" })
            course_gid = os.stat('/courses/{}'.format(course_slug)).st_gid
            cmds.insert(0, "addgroup --gid {} {}".format(course_gid, 'jupyter-'+course_slug))
            if 'NB_GID' in environ:
                environ['NB_GID'] = str(course_gid)
            else:
                spawner.singleuser_supplemental_gids.append(course_gid)
        else:
            cmds.insert(0, "disable_formgrader.sh")

        # Student config
        if username in course_data.get('students', {}):
            allow_spawn = True

        if not allow_spawn and course_data.get('private', False):
            raise RuntimeError("You ({}) are not allowed to use the {} environment".format(username, course_slug))

    # Common final setup
    spawner.cmd = ["bash", "-x", "-c", ] + [" && ".join(cmds)]

    
c.KubeSpawner.pre_spawn_hook = pre_spawn_hook

# Culler service
c.JupyterHub.services = [
  {
    'name': 'cull-idle',
    'admin': True,
    'command': 'python3 /cull_idle_servers.py --timeout=3600 --cull_every=300'.split(),
  }
]

