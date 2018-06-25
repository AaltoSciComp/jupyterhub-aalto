import socket
import os

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

c.PAMAuthenticator.open_sessions = False

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

#c.KubeSpawner.uid = 1001
#c.KubeSpawner.singleuser_uid = 1001

# profile_list --> use this instead of ProfileSpawner ?
def pre_spawn_hook(spawner):
  if (spawner.user.name == "test"):
    spawner.volume_mounts.append({ "mountPath": "/course", "name": "course" })
  if (spawner.user.name == "student"):
    spawner.cmd = ["bash", "-c", "disable_formgrader.sh && start-notebook.sh"]
  course = spawner.course_slug
  #self.gid = xxx
  #storage_capacity = ???
  # For instructors
  #supplemental_gids = xxx  # course instructors
c.KubeSpawner.pre_spawn_hook = pre_spawn_hook

c.Authenticator.admin_users = ['test']

# Culler service
c.JupyterHub.services = [
  {
    'name': 'cull-idle',
    'admin': True,
    'command': 'python3 /cull_idle_servers.py --timeout=3600 --cull_every=300'.split(),
  }
]

