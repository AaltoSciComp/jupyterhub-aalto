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

for f in os.listdir('/courses'):
  if (f.endswith('.yaml')):
    course_data = yaml.load(open('/courses/{}'.format(f)))
    print(course_data)
    for username in course_data.get('students', []):
      c.Authenticator.whitelist.add(username)
    for username in course_data.get('instructors', []):
      c.Authenticator.whitelist.add(username)

# Spawner config
c.KubeSpawner.start_timeout = 60 * 5
c.KubeSpawner.singleuser_image_spec = 'nbgrader-mlbp'
c.KubeSpawner.hub_connect_ip = host_ip
c.JupyterHub.hub_connect_ip = c.KubeSpawner.hub_connect_ip
c.KubeSpawner.hub_connect_port = 80
c.KubeSpawner.http_timeout = 60 * 5
# Volume mounts
c.KubeSpawner.volumes = [
  {
    "name": "user",
    "nfs": {
      "server": "jupyter-k8s-admin.cs.aalto.fi",
      "path": "/srv/jupyter-tw/user/{username}"
    }
  },
  {
    "name": "exchange",
    "nfs": {
      "server": "jupyter-k8s-admin.cs.aalto.fi",
      "path": "/srv/jupyter-tw/exchange"
    }
  },
  {
    "name": "course",
    "nfs": {
      "server": "jupyter-k8s-admin.cs.aalto.fi",
      "path": "/srv/jupyter-tw/course"
    }
  }
]
c.KubeSpawner.volume_mounts = [
  { "mountPath": "/user", "name": "user" },
  { "mountPath": "/exchange", "name": "exchange" }
]

c.KubeSpawner.singleuser_working_dir = '/user'

c.KubeSpawner.profile_list = [{
  'display_name': 'MLBP 2018',
  'kubespawner_override': {
    # if callable is here, set spawner.k = v(spawner)
    #'image_spec': 'training/python:label',
    #'cpu_limit': 1,
    #'mem_limit': '512M',
    'course_slug': 'mlbp2018',
  }
}]

def create_user_dir(username, uid):
  os.system('ssh jupyter-k8s-admin.cs.aalto.fi "/root/jupyterhub/scripts/create_user_dir.sh {0} {1}"'.format(username, uid))

# profile_list --> use this instead of ProfileSpawner ?
def pre_spawn_hook(spawner):
  # set notebook container user
  username = spawner.user.name
  uid = pwd.getpwnam(username).pw_uid
  c.KubeSpawner.singleuser_uid = uid

  course = spawner.course_slug
  course_data = yaml.load("{}.yaml".format(course))

  if username in course_data.get('instructors', {}):
    spawner.volume_mounts.append({ "mountPath": "/course", "name": "course" })
  elif username in course_data.get('students', {}):
    spawner.cmd = ["bash", "-c", "disable_formgrader.sh && start-notebook.sh"]
  else:
    pass # TODO: Stop user access, preferably just don't show logged in user the course in the profile list

  create_user_dir(username, uid) # TODO: Define path / server / type in yaml?
  
  #self.gid = xxx
  #storage_capacity = ???
  # For instructors
  #supplemental_gids = xxx  # course instructors
c.KubeSpawner.pre_spawn_hook = pre_spawn_hook

# Culler service
c.JupyterHub.services = [
  {
    'name': 'cull-idle',
    'admin': True,
    'command': 'python3 /cull_idle_servers.py --timeout=3600 --cull_every=300'.split(),
  }
]

