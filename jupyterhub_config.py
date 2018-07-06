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

# Volume mounts
DEFAULT_VOLUMES = [
  {
    "name": "user",
    "nfs": {
      "server": "jhnas.org.aalto.fi",
      "path": "/vol/jupyter/user/{username}"
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
  { "mountPath": "/user", "name": "user" },
  #{ "mountPath": "/exchange", "name": "exchange" }
]
c.KubeSpawner.volumes = DEFAULT_VOLUMES
c.KubeSpawner.volume_mounts = DEFAULT_VOLUME_MOUNTS

c.KubeSpawner.singleuser_working_dir = '/user'


PROFILE_LIST = [
    {'display_name': 'Generic',
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
    } for (course_slug, course_data) in COURSES.items()])
c.KubeSpawner.profile_list = PROFILE_LIST
if len(c.KubeSpawner.profile_list) < 2:
    raise RuntimeError("Startup error: no profiles found")


def create_user_dir(username, uid):
  os.system('ssh jupyter-k8s-admin.cs.aalto.fi "/root/jupyterhub/scripts/create_user_dir.sh {0} {1}"'.format(username, uid))

# profile_list --> use this instead of ProfileSpawner ?
def pre_spawn_hook(spawner):
    # set notebook container user
    username = spawner.user.name
    userinfo = pwd.getpwnam(username)
    uid = userinfo.pw_uid
    homedir = userinfo.pw_dir
    if homedir.startswith('/u/'): homedir = homedir[3:]
    spawner.singleuser_uid = uid
    spawner.singleuser_supplemental_gids = [100] # group 'users' required in order to write config files etc
    #self.gid = xxx
    #storage_capacity = ???

    create_user_dir(username, uid) # TODO: Define path / server / type in yaml?


    # Course configuration - only if it is a course
    course_slug = spawner.course_slug
    if course_slug:
        course_data = COURSES[course_slug]
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
        if username in course_data.get('instructors', {}):
            spawner.volumes.append({
                "name": "course",
                "nfs": {
                    "server": "jhnas.org.aalto.fi",
                    "path": "/vol/jupyter/course/{}".format(course_slug)
                }
            })
            spawner.volume_mounts.append({ "mountPath": "/course", "name": "course" })
            #supplemental_gids = os.stat('/courses/{}'.format(course_slug)).st_gid
        else:
            spawner.cmd = ["bash", "-c", "disable_formgrader.sh && start-notebook.sh"]

        # Student config
        if username in course_data.get('students', {}):
            pass
    
c.KubeSpawner.pre_spawn_hook = pre_spawn_hook

# Culler service
c.JupyterHub.services = [
  {
    'name': 'cull-idle',
    'admin': True,
    'command': 'python3 /cull_idle_servers.py --timeout=3600 --cull_every=300'.split(),
  }
]

