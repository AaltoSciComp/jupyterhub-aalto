import copy
import datetime
from datetime import date
import glob
import grp
import os
from pprint import pprint
import pwd # for resolving username --> uid
import re
import shlex
import socket
import subprocess
import sys
import time
import traceback
import yaml
from kubernetes import client, config
import kubernetes.client.rest
from base64 import b64encode
import secrets
import string

# c.JupyterHub.log_level = 'DEBUG'

IMAGE_DEFAULT = 'aaltoscienceit/notebook-server:4.1.1'         # for generic images
IMAGE_COURSE_DEFAULT = 'aaltoscienceit/notebook-server:4.1.1'  # for courses
IMAGE_DEFAULT_R = 'aaltoscienceit/notebook-server-r-ubuntu:4.1.0'
IMAGE_DEFAULT_JULIA = 'aaltoscienceit/notebook-server-julia:4.1.0'
IMAGE_DEFAULT_CUDA = 'aaltoscienceit/notebook-server-cuda:1.8.8'
#IMAGE_TESTING = 'aaltoscienceit/notebook-server:1.0.6'
IMAGES_OLD = [
    #'aaltoscienceit/notebook-server:1.8.8',
]

# NOTE: Image definitions have been moved to jupyterhub-aalto-course-meta/IMAGES.py
#       Do not define images here
#IMAGES_BYDATE = {
#    # Add new to BOTTOM.
#    'standard': [
#        (date(2019, 11, 11), 'aaltoscienceit/notebook-server:1.8.8'),
#    ],
#}
DEFAULT_MEM_GUARANTEE = 512 * 2**20
DEFAULT_CPU_GUARANTEE = .10
DEFAULT_MEM_LIMIT = 5 * 2**30
DEFAULT_CPU_LIMIT = 4
DEFAULT_TIMEOUT = 3600 * 1
DEFAULT_TIMELIMIT = 3600 * 8
INSTRUCTOR_MEM_LIMIT = DEFAULT_MEM_LIMIT
INSTRUCTOR_CPU_LIMIT = DEFAULT_CPU_LIMIT
INSTRUCTOR_MEM_GUARANTEE = 1 * 2**30
INSTRUCTOR_CPU_GUARANTEE = DEFAULT_CPU_GUARANTEE
ROOT_THEN_SU = True
MOUNT_EXTRA_COURSES = True


DEFAULT_NODE_SELECTOR = { }
DEFAULT_TOLERATIONS = [
    {'key': 'cs-aalto/app', 'value': 'jupyter', 'operator': 'Equal', 'effect': 'NoSchedule'},
    ]
EMPTY_PROFILE = {'node_selector': DEFAULT_NODE_SELECTOR,
                 'tolerations': DEFAULT_TOLERATIONS,
                 'default_url': 'tree/notebooks',
                 'image': IMAGE_DEFAULT,
                }

def unique_suffix(base, other):
    """Return the unique suffix of other, relative to base."""
    if 'registry.cs.aalto.fi' in other:
        base = base.replace('aaltoscienceit', 'registry.cs.aalto.fi/jupyter')
    prefix = os.path.commonprefix([base, other])
    suffix = other[len(prefix):]
    if ':' not in suffix:
        suffix = other.rsplit(':', 1)[-1]
    return suffix


# Default profile list
PROFILE_LIST_DEFAULT = [
    {'slug': 'general-python',
     'display_name': 'Python: General use (JupyterLab) '
                      '<font color="#999999">%s</font>'%(IMAGE_DEFAULT.split(':')[-1]),
     'default': True,
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True, },
    },
    {'slug': 'general-python-notebook',
     'display_name': 'Python: General use (classic notebook) '
                     '<font color="#999999">%s</font>'%(IMAGE_DEFAULT.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': ''},
    },
    {'slug': 'general-r',
     'display_name': 'R: General use (JupyterLab) '
                     '<font color="#999999">%s</font>'%(IMAGE_DEFAULT_R.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True,
                               'image': IMAGE_DEFAULT_R, },
    },
    {'slug': 'general-julia',
     'display_name': 'Julia: General use (JupyterLab) '
                     '<font color="#999999">%s</font>'%(IMAGE_DEFAULT_JULIA.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True,
                               'image': IMAGE_DEFAULT_JULIA,},
    },
]
if 'IMAGE_TESTING' in globals():
    PROFILE_LIST_DEFAULT.append(
    {'display_name': '(testing) Python: General use (JupyterLab) '
                     '<font color="#999999">%s</font>'%(IMAGE_TESTING.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True,
                               'image': IMAGE_TESTING, }
    })
for image in IMAGES_OLD:
    PROFILE_LIST_DEFAULT.append(
    {'display_name': '<font color="#AAAAAA">Old version (JupyterLab)</font> '
                     '<font color="#999999">%s</font>'%(unique_suffix(IMAGE_DEFAULT, image)),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True,
                               'image': image, }
    })
PROFILE_LIST_DEFAULT_BOTTOM = [
    {'display_name': 'GPU testing '
                      '<font color="#999999">%s</font>'%(IMAGE_DEFAULT_CUDA.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True,
                              'image':IMAGE_DEFAULT_CUDA, 'xx_name': 'gpu_testing',
                              'node_selector':{'cs-aalto/gpu': 'true'},
                              'tolerations':[{'key':'cs-aalto/gpu', 'operator':"Exists", 'effect':"NoSchedule"}, *DEFAULT_TOLERATIONS],}
    },
]


# Set up generic without jupyterlab
# RStan





c.Application.log_level = 'INFO'

# Basic JupyterHub config
#c.JupyterHub.bind_url = 'http://:8000'   # we have separate proxy now
c.JupyterHub.hub_bind_url = 'http://0.0.0.0:8081'
c.JupyterHub.hub_connect_ip = os.environ['JUPYTERHUB_SVC_SERVICE_HOST']
c.JupyterHub.cleanup_servers = False  # leave servers running if hub restarts
c.JupyterHub.template_paths = ["/srv/jupyterhub/templates/"]
c.JupyterHub.last_activity_interval = 180  # default 300
c.JupyterHub.authenticate_prometheus = False
# Proxy config
#c.ConfigurableHTTPProxy.api_url = 'http://jupyterhub-chp-svc.default:8001'  # 10.104.184.140
c.ConfigurableHTTPProxy.api_url = 'http://%s:8001'%os.environ['JUPYTERHUB_CHP_SVC_SERVICE_HOST']
c.ConfigurableHTTPProxy.auth_token = open('/srv/jupyterhub/chp-secret.txt').read()
#print('auth_token=', repr(c.ConfigurableHTTPProxy.auth_token), file=sys.stderr)
c.ConfigurableHTTPProxy.should_start = False


# Authentication
from jupyterhub.auth import PAMAuthenticator
class NormalizingPAMAuthenticator(PAMAuthenticator):
    def normalize_username(self, username):
        # pass through uid to ensure that all names that
        # correspond to one uid map to the same jupyterhub user
        uid = pwd.getpwnam(username).pw_uid
        return super().normalize_username(pwd.getpwuid(uid).pw_name)
c.JupyterHub.authenticator_class = NormalizingPAMAuthenticator
#c.Authenticator.delete_invalid_users = True  # delete users once no longer in Aalto AD
c.Authenticator.admin_users = {'darstr1', 'laines5', 'vienama1'}
USER_RE = re.compile('^[a-z0-9.]+$')


# Spawner config
c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'
c.KubeSpawner.start_timeout = 60 * 5
c.KubeSpawner.hub_connect_port = 8081
c.KubeSpawner.http_timeout = 20
c.KubeSpawner.disable_user_config = True
c.KubeSpawner.common_labels = { "cs-aalto/app": "notebook-server" }
c.KubeSpawner.poll_interval = 150  # default 30, check each pod for aliveness this often

# User environment config
c.KubeSpawner.image = IMAGE_DEFAULT
c.KubeSpawner.default_url = "tree/notebooks"
c.KubeSpawner.notebook_dir = "/"
# doesn't work, because we start as root, this happens as root but we
# have root_squash.
#c.KubeSpawner.singleuser_working_dir = '/notebooks'
# Note: instructors get different limits, see below.
c.KubeSpawner.cpu_limit = DEFAULT_CPU_LIMIT
c.KubeSpawner.mem_limit = DEFAULT_MEM_LIMIT
c.KubeSpawner.cpu_guarantee = DEFAULT_CPU_GUARANTEE
c.KubeSpawner.mem_guarantee = DEFAULT_MEM_GUARANTEE


# Volume mounts
DEFAULT_VOLUMES = [
  {"name": "jupyter-nfs",
   'persistentVolumeClaim':{'claimName': 'jupyter-nfs'}},
]
DEFAULT_VOLUME_MOUNTS = [
  {"name": "jupyter-nfs", "mountPath": "/notebooks", "subPath": "u/{uid_last2digits}/{username}", "readOnly": False},
  {"name": "jupyter-nfs", "mountPath": "/mnt/jupyter/shareddata", "subPath": "shareddata/", "readOnly":False},
  {"name": "jupyter-nfs", "mountPath": "/m/jhnas/jupyter/shareddata", "subPath": "shareddata/", "readOnly":False},
  {"name": "jupyter-nfs", "mountPath": "/m/jhnas/jupyter/software", "subPath": "software/", "readOnly":True},
]
c.KubeSpawner.volumes = DEFAULT_VOLUMES
c.KubeSpawner.volume_mounts = DEFAULT_VOLUME_MOUNTS

# Kubernetes client config for job token management
config.load_incluster_config()
k8s_api = client.CoreV1Api()

# Find all of our courses and profiles
COURSES = { }
COURSES_TS = None
METADIR = "/courses/meta"
GROUPS = { }     # map username->{group:name, gid:number} for all allowed courses.
def GET_COURSES():
    """Update the global COURSES dictionary.

    Wrapped in a function so that we can update even while the process
    is running.  Has some basic caching, so that we do not constantly
    regenerate this data.

    """
    global COURSES, COURSES_TS
    global GROUPS

    # Cache, don't unconditionally reload every time.
    # Always return cached if we have last loaded courses less than 10 seconds ago
    if COURSES_TS and COURSES_TS > time.time() - 10:
        return COURSES
    latest_yaml_ts = max(os.stat(course_file).st_mtime
                         for course_file in glob.glob(os.path.join(METADIR, '*.yaml')))
    # If all course timestamps are older than COURSES_TS, return cached copy.
    #    ... but if it is more than one hour old, never return cached copy.
    if COURSES_TS and COURSES_TS > latest_yaml_ts and not COURSES_TS < time.time() - 3600:
        return COURSES

    # Regenerate the course dict from yamls on disk.
    #c.JupyterHub.log.debug("Re-generating course data")
    COURSES_TS = time.time()
    courses = { }
    groups = { }
    # First round: load raw data with users and so on.
    for course_file in glob.glob(os.path.join(METADIR, '*.yaml')):
        try:
            course_slug = os.path.splitext(os.path.basename(course_file))[0]
            if course_slug.endswith('-users'):
                course_slug = course_slug[:-6]
            course_data = yaml.safe_load(open(course_file))
            #print(course_slug, course_data, file=sys.stderr)
            if course_slug not in courses:
                courses[course_slug] = { }
            if 'instructors' in course_data: course_data['instructors'] = set(course_data['instructors'])
            if 'students'    in course_data: course_data['students']    = set(course_data['students'])
            courses[course_slug].update(course_data)
            #print(course_slug, course_data, file=sys.stderr)
        except:
            exc_info = sys.exc_info()
            print("ERROR: error loading yaml file {}".format(course_file), file=sys.stderr)
            print("".join(traceback.format_exception(*exc_info)).decode(), file=sys.stderr)

    # Second round: make the data consistent:
    # - add course GIDs by looking up via `getent group`.
    # - Look up extra instructors by using `getent group`
    for course_slug, course_data in courses.items():
        if 'instructors' not in course_data: course_data['instructors'] = set()
        if 'students'    not in course_data: course_data['students']    = set()
        if course_data.get('gid') is None:
            # No filesystem mounts here
            course_data['gid'] = None
        else:
            try:
                course_data['instructors'] |= set(grp.getgrnam('jupyter-'+course_slug).gr_mem)
                # Testcourse gets all instructors
                courses['testcourse']['instructors'] |= set(grp.getgrnam('jupyter-'+course_slug).gr_mem)
            except KeyError:
                print("ERROR: group {} can not look up group info".format(course_slug), file=sys.stderr)
            # Add a group directory mapping (instructor) -> {group, gid} of allowed courses
            for instructor in course_data['instructors']:
                groups.setdefault(instructor, set()).add((course_slug, course_data['gid']))

    # Set global variable from new local variable.
    COURSES = courses
    GROUPS = groups
    return COURSES
# Run it once to set the course data at startup.
GET_COURSES()

UPDATE_IMAGES_TS = None
IMAGES_UPDATEFILE = os.path.join(METADIR, 'IMAGES.py')
def UPDATE_IMAGES():
    """Update the default images based on a timeout"""
    global UPDATE_IMAGES_TS

    # If the definition file doesn't exist, do nothing
    if not os.path.exists(IMAGES_UPDATEFILE):
        return
    # Cache, don't unconditionally reload every time.
    # Always return cached if we have last loaded courses less than 10 seconds ago
    if UPDATE_IMAGES_TS and UPDATE_IMAGES_TS > time.time() - 10:
        return
    last_ts = os.stat(IMAGES_UPDATEFILE).st_mtime
    # If timestamp is older than cached, return cached copy.
    #    ... but if it is more than one hour old, never return cached copy
    if UPDATE_IMAGES_TS and UPDATE_IMAGES_TS > last_ts and not  UPDATE_IMAGES_TS < time.time() - 3600:
        return
    UPDATE_IMAGES_TS = time.time()

    try:
        exec(open(IMAGES_UPDATEFILE).read(), globals())
    except:
        exc_info = sys.exc_info()
        print("ERROR: error loading file {}".format(IMAGES_UPDATEFILE), file=sys.stderr)
        print("".join(traceback.format_exception(*exc_info)).decode(), file=sys.stderr)



def select_image(image_name):
    """Get an image name from the name in the argument

    Usually, it will be the same.  But, if an all-uppercase name such as
    DEFAULT is given, then use IMAGE_$name from globals() instead.  This
    allows certain courses to be continually updated.
    """
    # Find a date-based image
    if (isinstance(image_name, (tuple, list))
        and isinstance(image_name[0], str)
        and isinstance(image_name[1], date)
       ):
        # Select the right class - standard, r-ubuntu, etc.
        image_list = IMAGES_BYDATE[image_name[0]]
        image_date = image_name[1]
        # Naive algorithm, we can't use bisect.bisect because we don't have a
        # pure key-based lookup and it doesn't have a key= function.
        # Search backwards, look for first (actually last in the list) image
        # equal to or less the date we give.
        for i in range(len(image_list)-1, -1, -1):
            if image_list[i][0] <= image_date:
                return image_list[i][1]
        # Not found, return nothing.
        return IMAGE_COURSE_DEFAULT

    # If the image name is a string and all uppercase, look up the global
    # variable IMAGE_{name} and return that.
    if isinstance(image_name, str) and image_name.isupper():
        if 'IMAGE_'+image_name in globals():
            return globals()['IMAGE_'+image_name]
    # Otherwise: just use the name as-is.
    return image_name

def get_profile_list(spawner):
    """gerenate the k8s profile_list.
    """
    UPDATE_IMAGES()
    #c.JupyterHub.log.debug("Recreating profile list")
    # All courses
    profile_list = [ ]
    for course_slug, course_data in GET_COURSES().items():
        is_student = spawner.user.name in course_data.get('students', [])
        is_instructor = spawner.user.name in course_data.get('instructors', [])
        is_teststudent = spawner.user.name in {'student1', 'student2', 'student3'}
        is_admin = spawner.user.admin
        is_archive = course_data.get('archive', False)
        is_private = course_data.get('private', False)
        course_notes = ""
        if is_archive:
            continue
        if is_private:
            if not (is_instructor or is_student or is_teststudent or is_admin):
                continue
            if not is_student:
                course_notes = ' <font color="brown">(not public)</font>'
        display_name = course_data.get('name', course_slug)
        profile_list.append({
            'slug': course_slug,
            'display_name': display_name + course_notes + ' <font color="#999999">' + unique_suffix(IMAGE_DEFAULT, IMAGE_COURSE_DEFAULT)+'</font>',
            'kubespawner_override': {
                **EMPTY_PROFILE,
                'course_slug': course_slug,
                'image': IMAGE_COURSE_DEFAULT,
                **course_data.get('kubespawner_override', {}),
                },
            'x_jupyter_enable_lab': False,
            })
        if 'image' in course_data:
            course_image = select_image(course_data['image'])
            profile = profile_list[-1]   # REFERENCE
            profile['display_name'] = display_name + course_notes + ' <font color="#999999">' + unique_suffix(IMAGE_DEFAULT, course_image)+'</font>'
            profile['kubespawner_override']['image'] = course_image
        if is_instructor or is_admin:
            profile = copy.deepcopy(profile_list[-1])  # COPY AND RE-APPEND
            profile['display_name'] = display_name + ' <font color="blue">(instructor)</font>'
            profile['slug'] = profile['slug'] + '-instructor'
            if 'image_instructor' in course_data:
                course_image_instructor = select_image(course_data['image_instructor'])
                profile['display_name'] = profile['display_name'] + ' <font color="#999999">' + unique_suffix(IMAGE_DEFAULT, course_image_instructor)+'</font>'
                profile['kubespawner_override']['image'] = course_image_instructor
            profile['kubespawner_override']['as_instructor'] = True
            profile_list.append(profile)

    #pprint(GET_COURSES().items(), stream=sys.stderr)
    #pprint(spawner.user.name, stream=sys.stderr)
    #pprint(profile_list, stream=sys.stderr)

    profile_list.sort(key=lambda x: x['display_name'])
    profile_list = copy.deepcopy(PROFILE_LIST_DEFAULT) + profile_list + copy.deepcopy(PROFILE_LIST_DEFAULT_BOTTOM)

    return profile_list
# In next version of kubespawner, leave as callable to regen every
# time, without restart.
c.KubeSpawner.profile_list = get_profile_list  #(None)
#if len(c.KubeSpawner.profile_list) < 2:
#    raise RuntimeError("Startup error: no course profiles found")




def create_user_dir(username, uid, human_name="", log=None):
    # create_user_dir.sh knows how to compete directory from (uid, username)
    #os.system('ssh jupyter-k8s-admin.cs.aalto.fi "/root/jupyterhub/scripts/create_user_dir.sh {0} {1}"'.format(username, uid))
    human_name = re.sub('[^\w -]*', '', human_name, flags=re.I)
    human_name = human_name.replace(' ', '++')
    ret = subprocess.run(
        ['ssh', 'jupyter-manager.cs.aalto.fi',
         "/root/jupyterhub-aalto/scripts/create_user_dir.sh", shlex.quote(username), str(uid), shlex.quote(human_name)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if ret.returncode != 0:
        log.error('create_user_dir failed for %s %s', username, uid)
        log.error(ret.stdout.decode())
    else:
        log.debug('create_user_dir: %s %s', username, uid)
        log.debug(ret.stdout.decode())


async def pre_spawn_hook(spawner):
    # Note: spawners Python objects are persistent, and if you don't
    # clear certain attributes, they will persist across restarts!
    #spawner.node_selector = { }
    #spawner.tolerations = [ ]
    #spawner.default_url = c.KubeSpawner.default_url
    await spawner.load_user_options()
    spawner._profile_list = [ ]
    spawner.create_groups = [ ]
    spawner.environment = environ = { }  # override env

    # Get basic info
    username = spawner.user.name
    if not USER_RE.match(username):
        raise RuntimeError("Invalid username: %s, logout and use lowercase Aalto username."%username)
    userinfo = pwd.getpwnam(username)
    homedir = userinfo.pw_dir
    if homedir.startswith('/u/'): homedir = homedir[3:]
    uid = userinfo.pw_uid
    human_name = userinfo.pw_gecos
    uid_last2digits = "%02d"%(uid%100)
    spawner.log.info("pre_spawn_hook: %s starting course_slug=%s, slug=%s",
                     username,
                     getattr(spawner, 'course_slug', 'None'),
                     getattr(spawner, 'slug', 'None'))


    # Make a copy of the *default* class volumes.  The "spawner" object
    # is constantly reused.
    spawner.volumes = copy.deepcopy(DEFAULT_VOLUMES)
    spawner.volume_mounts = copy.deepcopy(DEFAULT_VOLUME_MOUNTS)
    assert 'uid_last2digits' in spawner.volume_mounts[0]['subPath']
    #print(spawner.volumes, file=sys.stderr)
    spawner.volume_mounts[0]['subPath'] = spawner.volume_mounts[0]['subPath'].format(username=username, uid_last2digits=uid_last2digits)
    notebook_path = "/m/jhnas/jupyter/u/{uid_last2digits}/{username}/".format(username=username, uid_last2digits=uid_last2digits)
    spawner.volume_mounts.append({"mountPath": notebook_path,
                                  "subPath": "u/{uid_last2digits}/{username}".format(username=username, uid_last2digits=uid_last2digits),
                                  "name": "jupyter-nfs",
                                  "readOnly": False})
    environ['NB_NOTEBOOK_PATH'] = notebook_path
    #print(spawner.volumes, file=sys.stderr)

    # Set basic spawner properties
    #storage_capacity = ???
    environ['AALTO_JUPYTERHUB'] = '1'
    environ['PYTHONPATH'] = '/m/jhnas/jupyter/software/pymod/'  # Remove once all notebooks have the newer hooks.
    environ['TZ'] = os.environ.get('TZ', 'Europe/Helsinki')
    cmds = [ ]
    # Remove the .jupyter config that is already there
    #cmds.append("echo 'umask 0007' >> /home/jovyan/.bashrc")
    #cmds.append("echo 'umask 0007' >> /home/jovyan/.profile")
    #cmds.append("pip install --upgrade --no-deps https://github.com/AaltoScienceIT/nbgrader/archive/live.zip")
    if getattr(spawner, 'x_jupyter_enable_lab', False):
        environ['JUPYTER_ENABLE_LAB'] = 'true'
        spawner.default_url = "lab/tree/notebooks/"
    #cmds.append('jupyter labextension enable @jupyterlab/google-drive')
    # Install gpuplug in the GPU images
    if spawner.node_selector and 'cs-aalto/gpu' in spawner.node_selector:
        cmds.append("pip install --upgrade https://github.com/AaltoScienceIT/gpuplug/archive/master.zip")
        spawner.volumes.append({
            "name": "gpuplug-sock",
            "hostPath": {
                "path": "/run/gpuplug.sock",
                "type": "Socket",
            }
        })
        spawner.volume_mounts.append({
            "mountPath": "/run/gpuplug.sock",
            "name": "gpuplug-sock"
        })


    # Extra Aalto config
    #environ['AALTO_EXTRA_HOME_LINKS'] = '.ssh/'
    # Hack to change validation timeout to 120
    # Some images still have python3.6, some 3.7; let's deal with it
    #cmds.append(r"PYTHON_DIR=$(ls -d /opt/conda/lib/python3.*)")
    #cmds.append(r"sed -i -E 's#(timeout = Integer\()(30)(,)#\1240\3#' ${PYTHON_DIR}/site-packages/nbconvert/preprocessors/execute.py")

    if uid < 1000: raise ValueError("uid can not be less than 1000 (is {})"%uid)
    spawner.working_dir = '/'

    # Note: current (summer 2018) conda version of kubespawner does
    # not use "uid" or "gid" options as you see in the latest
    # kubespawner.

    # Default setup of /etc/passwd: jovyan:x:1000:0
    # Default setup of /etc/group: users:x:100

    if not ROOT_THEN_SU:
        assert False  # This must be tested before using, not in regular use
        # Manually run as uid from outside the container
        spawner.uid = uid
        # default of user in docker image (note: not in image kubespawer yet!)
        spawner.gid = spawner.fs_gid = 70000
        # group 'users' required in order to write config files etc
        spawner.supplemental_gids = [70000, 100]
        # This must be set so that nbgrader has right username.  TODO: does it work?
        environ['NB_USER'] = username
    else:
        # To do this, you should have /home/$username exist...
        environ['NB_USER'] = username
        environ['NB_UID'] = str(uid)
        environ['NB_GID'] = '70000'
        environ['NB_GROUP'] = 'domain-users'
        #environ['GRANT_SUDO'] = 'yes'
        # The default jupyter image will use root access in order to su to the user as defined above.
        spawner.uid = 0
        # Fix permissions.  Uses NB_GID only, and should not run on any NFS filesystems!
        #cmds.append("fix-permissions /home/jovyan")
        #cmds.append("fix-permissions $CONDA_DIR")

        # add default user to group 100 for file access. (Required
        # because sudo prevents supplemental_gids from taking effect
        # after the sudo).  The "jovyan" user is renamed to $NB_USER
        # on startup.
        #cmds.append("adduser jovyan users")

    create_user_dir(username, uid, human_name=human_name, log=spawner.log)
    #cmds.append(r'echo "if [ \"\$SHLVL\" = 1 -a \"\$PWD\" = \"\$HOME\" ] ; then cd /notebooks ; fi" >> /home/jovyan/.profile')
    cmds.append(r'echo "if [ \"\$SHLVL\" = 1 -a \( \"\$PWD\" = \"\$HOME\" -o \"\$PWD\" = / \)  ] ; then cd /notebooks ; fi" >> /home/jovyan/.bashrc')
    cmds.append(r'echo "nbgrader-instructor-exchange() { nbgrader \$1 --Exchange.root=/course/test-instructor-exchange/ \${@:2} ; }" >> /home/jovyan/.bashrc')

    #for line in ['[user]',
    #             '    name = {}'.format(fullname),
    #             '    email = {}'.format(email),
    #             ]:
    #    cmds.append(r"echo '{}' >> /home/jovyan/.gitconfig".format(line))
    #    cmds.append("fix-permissions /home/jovyan/.gitconfig")

    course_slug = getattr(spawner, 'course_slug', '')
    as_instructor = False
    # We are not part of a course, so do only generic stuff
    # if gid is None, we have a course definition but no course data (only setting image)
    if not course_slug or GET_COURSES()[course_slug]['gid'] is None:
        cmds.append("disable_formgrader.sh")
        # The pod_name must always be set, otherwise it uses the last pod name.
        spawner.pod_name = 'jupyter-{}{}'.format(username, '-'+spawner.name if spawner.name else '')

    # Course configuration - only if it is a course
    else:
        spawner.log.debug("pre_spawn_hook: course %s", course_slug)
        environ['NB_COURSE'] = course_slug
        course_data = GET_COURSES()[course_slug]
        spawner.pod_name = 'jupyter-{}-{}{}'.format(username, course_slug, '-'+spawner.name if spawner.name else '')
        if course_data.get('jupyterlab', False):
            environ['JUPYTER_ENABLE_LAB'] = 'true'
            spawner.default_url = "lab/tree/notebooks/"

        # Add course exchange
        # /srv/nbgrader/exchange is the default path
        exchange_readonly = (course_data.get('restrict_submit', False) and 'username' not in course_data.get('students', {})
                                                                       and 'username' not in course_data.get('instructors', {}))
        spawner.volume_mounts.append({"mountPath": "/srv/nbgrader/exchange",
                                      "name": "jupyter-nfs",
                                      "subPath": "exchange/{}".format(course_slug),
                                      "readOnly": exchange_readonly})
        # Add coursedata dir, if it exists
        if course_data.get('datadir', False):
            spawner.volume_mounts.append({"mountPath": "/coursedata",
                                          "subPath": "course/{}/data/".format(course_slug),
                                          "name": "jupyter-nfs",
                                          "readOnly": ((username not in course_data.get('instructors', {}))
                                                       and not course_data.get('datadir_readwrite', False)
                                                       and not getattr(spawner, 'as_instructor', False)
                                                       ),
                                          })
            environ['COURSEDATA'] = '/coursedata/'


        # Jupyter/nbgrader config
        for line in ['',
                     'c = get_config()',
                     'c.CourseDirectory.root = "/course"',
                     'c.CourseDirectory.groupshared = True',
                     'c.CourseDirectory.course_id = "{}"'.format(course_slug),
                     'c.Exchange.course_id = "{}"'.format(course_slug),
                     'c.CourseDirectory.ignore = [".ipynb_checkpoints", "*.pyc*", "__pycache__", "feedback", ".*"]',
                     'c.CourseDirectory.max_file_size = int(30*1024*(1024/1000.))+1',  #KB, translate to KiB
                     'c.Exchange.assignment_dir = "/notebooks/"',
                     'c.Exchange.timezone = "Europe/Helsinki"',
                     'c.NbGraderAPI.timezone = "Europe/Helsinki"',
                     'c.AssignmentList.assignment_dir = "/notebooks/"',
                     'c.ExecutePreprocessor.timeout = 240',
                     'c.Execute.timeout = 240',
                     'c.Exchange.path_includes_course = True',
                     'c.Validator.validate_all = True',
                     'c.CollectApp.check_owner = False',
                     'c.ExportApp.plugin_class = "mycourses_exporter.MyCoursesExportPlugin"',
                     *course_data.get('nbgrader_config', '').split('\n'),
                     ]:
            cmds.append(r"echo '{}' >> /etc/jupyter/nbgrader_config.py".format(line))
        for line in ['',
                     'c.AssignmentList.assignment_dir = "/notebooks/"',
                     'c.ExecutePreprocessor.timeout = 240',
                     'c.Execute.timeout = 240',
                     ]:
            cmds.append(r"echo '{}' >> /etc/jupyter/jupyter_notebook_config.py".format(line))
        # RStudio config
        cmds.append(r'( test -d /etc/rstudio '
                    r'&& echo session-default-working-dir=~/notebooks/ >> /etc/rstudio/rsession.conf '
                    r'&& echo session-default-new-project-dir=~/notebooks/ >> /etc/rstudio/rsession.conf '
                    r'; true )')

        # Instructors
        allow_spawn = False
        if username in course_data.get('instructors', {}):
            allow_spawn = True
        if username in course_data.get('instructors', {}) and getattr(spawner, 'as_instructor', False):
            as_instructor = True
            spawner.log.info("pre_spawn_hook: User %s is an instructor for %s", username, course_slug)
            allow_spawn = True
            cmds.append("enable_formgrader.sh")
            environ['AALTO_NB_ENABLE_FORMGRADER'] = '1'
            # Instructors get the whole filesystem tree, because they
            # need to be able to access "/course", too.  Warning, you
            # will have different paths!  (fix later...)
            #spawner.cpu_limit = 1
            if isinstance(spawner.mem_limit, int) and isinstance(INSTRUCTOR_MEM_LIMIT, int):
                spawner.mem_limit = max(spawner.mem_limit, INSTRUCTOR_MEM_LIMIT)
            else:
                spawner.mem_limit = INSTRUCTOR_MEM_LIMIT
            spawner.cpu_guarantee = INSTRUCTOR_CPU_GUARANTEE
            spawner.mem_guarantee = INSTRUCTOR_MEM_GUARANTEE
            for line in ['c.NbGrader.logfile = "/course/.nbgraber.log"',
                        ]:
                cmds.append(r"echo '{}' >> /etc/jupyter/nbgrader_config.py".format(line))
            spawner.volume_mounts.append({"mountPath": "/course", "name": "jupyter-nfs", "subPath": "course/{}/files".format(course_slug)})
            spawner.volume_mounts.append({"mountPath": "/m/jhnas/jupyter/course/{}".format(course_slug), "name": "jupyter-nfs", "subPath": "course/{}".format(course_slug)})
            course_gid = int(course_data['gid'])
            spawner.log.debug("pre_spawn_hook: Course gid for {} is {}", course_slug, course_gid)
            cmds.append(r"umask 0007")  # also used through sudo
            environ['NB_UMASK'] = '0007'
            if ROOT_THEN_SU:
                # This branch happens only if we are root (see above)
                environ['NB_GID'] = str(course_gid)
                environ['NB_GROUP'] = 'jupyter-'+course_slug
                # The start.sh script renumbers the default group 100 to $NB_GID.  We rename it first.
                #cmds.append("groupmod -n {} users".format('jupyter-'+course_slug))
                # We *need* to be in group 100, because a lot of the
                # default files (conda, etc) are group=rw=100.  We add
                # a *duplicate* group 100, and only the first one is
                # renamed in the image (in the jupyter start.sh)
                #cmds.append("groupadd --gid 100 --non-unique users")
                #cmds.append("adduser jovyan users")
                cmds.append(r"sed -r -i 's/^(UMASK.*)022/\1007/' /etc/login.defs")
                cmds.append(r"echo Defaults umask=0007, umask_override >> /etc/sudoers")
                #cmds.append(r"{{ test ! -e /course/gradebook.db && sudo -u nobody touch /course/gradebook.db && chown {} /course/gradebook.db && chmod 660 /course/gradebook.db ; true ; }}".format(username))  # {{ and }} escape .format()
                #environ['NB_PRE_START_HOOK'] =  r"set -x ; sudo -u {username} bash -c 'set -x ; test ! -e /course/gradebook.db && touch /course/gradebook.db && chmod 660 /course/gradebook.db || true ;'".format(username=username)  # {{ and }} escape .format()
            else:
                spawner.gid = spawner.fs_gid = course_gid
                spawner.supplemental_gids.insert(0, course_gid)
                cmds.append(r"test ! -e /course/gradebook.db && touch /course/gradebook.db && chmod 660 /course/gradebook.db || true")
                # umask 0007 inserted above
        else:
            if getattr(spawner, 'as_instructor', False):
                spawner.log.info("pre_spawn_hook: %s tried to start %s as instructor, but was not allowed", username, course_slug)
            cmds.append("disable_formgrader.sh")

        # Student config
        if username in course_data.get('students', {}):
            spawner.log.info("pre_spawn_hook: User %s is a student for %s", username, course_slug)
            allow_spawn = True

        if spawner.user.admin:
            allow_spawn = True

        if not allow_spawn and course_data.get('private', False):
            spawner.log.info("pre_spawn_hook: User %s is blocked spawning %s", username, course_slug)
            raise RuntimeError("You ({}) are not allowed to use the {} environment.  Please contact the course instructors".format(username, course_slug))

    # Generate job token used for submitting remote node jobs
    token_string = secrets.token_hex(32)
    token_encoded = b64encode(bytes(token_string, "utf-8")).decode('utf-8')
    environ["JOB_TOKEN"] = token_string

    # Token name is like jobtoken-username-courseslug
    token_name_parts = ["jobtoken", username]
    if course_slug != '':
        token_name_parts.append(course_slug)
    token_name = '-'.join(token_name_parts)

    # Delete token, if it exists
    try:
        spawner.log.debug('pre_spawn_hook: %s: token: trying to delete %s', username, token_name)
        k8s_api.delete_namespaced_secret(token_name, "jupyter")
    except kubernetes.client.rest.ApiException:
        exc_info = sys.exc_info()
        spawner.log.info('pre_spawn_hook: %s: caught exception while deleting token: %s', username, token_name)
        #print("".join(traceback.format_exception(*exc_info)))
    # Create the actual token
    spawner.log.debug('pre_spawn_hook: %s: creating job token %s', username, token_name)
    k8s_api.create_namespaced_secret("jupyter", {
    "metadata": {
        "name": token_name,
        "namespace": "jupyter"
    },
        "data": {
            "job-token": token_encoded
        }
    })

    # import pprint
    # spawner.log.info("Before hooks: spawner.node_selector: %s", spawner.node_selector)

    # User- and course-specific hooks
    for hook_subpath in ['hooks-all.py',
                         'hooks-user/{}.py'.format(username),
                         'hooks-course/{}.py'.format(course_slug),
                        ]:
        hook_file = '/srv/jupyterhub/' + hook_subpath
        if os.path.exists(hook_file):
            spawner.log.info("pre_spawn_hook: Running %s", hook_file)
            exec(open(hook_file).read())

    # import pprint
    # spawner.log.info("After hooks: spawner.node_selector: %s", spawner.node_selector)
    # spawner.log.info("After hooks: spawner.__dict__: %s", pprint.pformat(spawner.__dict__))

    # Set number of processors, etc
    #pprint(vars(spawner), stream=sys.stderr)
    #pprint(spawner.volumes, stream=sys.stderr)
    for var in ['OMP_NUM_THREADS',
                'OPENBLAS_NUM_THREADS',
                'NUMEXPR_NUM_THREADS',
                'MKL_NUM_THREADS', ]:
        environ[var] = str(int(spawner.cpu_limit))
    # Aux groups for instructors (other mounts)
    if not (course_slug and not as_instructor) and ROOT_THEN_SU and MOUNT_EXTRA_COURSES:
        spawner.log.info('pre_spawn_hook: instructor %s is in the following groups: %s', username, GROUPS.get(username))
        for name, gid in GROUPS.get(username, []):
            try:
                if name == course_slug: continue
                spawner.create_groups.append((name, gid))
                spawner.supplemental_gids.append(gid)
                spawner.volume_mounts.append({"mountPath": '/m/jhnas/jupyter/course/{}/'.format(name),
                                              "subPath": "course/{}/".format(name),
                                              "name": "jupyter-nfs",
                                              "readOnly": COURSES[name].get('archived', False),})
            except:
                exc_info = sys.exc_info()
                spawner.log.critical("ERROR: setting up mount %s for %s", name, username)
                spawner.log.critical("".join(traceback.format_exception(*exc_info)).decode())

        if spawner.create_groups:
            environ['NB_CREATE_GROUPS'] = ','.join("jupyter-%s:%s"%(name,gid) for name,gid in spawner.create_groups)
        environ['NB_SUPPLEMENTARY_GROUPS'] = ','.join(str(x) for x in spawner.supplemental_gids)
    # Generate actual run commands and start
    cmds.append("source start-notebook.sh")   # args added later in KubeSpawner
    spawner.cmd = ["bash", "-x", "-c", ] + [" && ".join(cmds)]


def post_stop_hook(spawner):
    username = spawner.user.name
    spawner.log.info("post_stop_hook: %s stopping %s", username, getattr(spawner, 'course_slug', 'None'))
    course_slug = getattr(spawner, 'course_slug', '')

    # Delete the remote job token
    token_name_parts = ["jobtoken", username]
    if course_slug != '':
        token_name_parts.append(course_slug)
    token_name = '-'.join(token_name_parts)
    spawner.log.info('post_stop_hook: %s: trying to delete token_name=%s', username, token_name)
    try:
        k8s_api.delete_namespaced_secret(token_name, "jupyter")
    except kubernetes.client.rest.ApiException:
        spawner.log.info('post_stop_hook: %s: caught exception while deleting token: %s', username, token_name)

    spawner.log.info("post_stop_hook: %s stopped %s", username, course_slug or 'None')

from kubespawner.spawner import KubeSpawner
if 'kubespawner_get_state' not in globals():
    kubespawner_get_state  = KubeSpawner.get_state
    kubespawner_load_state = KubeSpawner.load_state
def get_state(spawner):
    """Add cull_max_time and cull_inactive_time to state, for use in culler

    This adds two extra variables to the state dictionary.  This is
    exposed to the culler via the API.  The culler script can then be
    modified to use this.  These variables are not loaded when state is
    restored - possible problem in future if state is re-saved.
    """
    state = kubespawner_get_state(spawner)
    for name in ['cull_max_age', 'cull_inactive_time', 'course_slug']:
        if hasattr(spawner, name):
            state[name] = getattr(spawner, name)
    return state
def load_state(spawner, state):
    kubespawner_load_state(spawner, state)
    for name in ['cull_max_age', 'cull_inactive_time', 'course_slug']:
        if name in state:
            setattr(spawner, name, state.get(name))
import jupyterhub.spawner
def clear_state(spawner):
    jupyterhub.spawner.Spawner.clear_state(spawner)
    for name in ['cull_max_age', 'cull_inactive_time', 'course_slug']:
        if hasattr(spawner, name):
            delattr(spawner, name)


c.KubeSpawner.pre_spawn_hook = pre_spawn_hook
c.KubeSpawner.post_stop_hook = post_stop_hook
KubeSpawner.get_state = get_state
KubeSpawner.load_state = load_state
KubeSpawner.clear_state = clear_state


# Culler service
c.JupyterHub.services = [
  {
    'name': 'cull-idle',
    'admin': True,
    'command': ('python3 /cull_idle_servers.py --timeout=%d --max-age=%d --cull_every=300 --concurrency=1'%(DEFAULT_TIMEOUT, DEFAULT_TIMELIMIT)).split(),
  },
  # Remove users from the DB every so often (1 week)... this has no practical effect.
  {
    'name': 'cull-inactive-users',
    'admin': True,
    'command': 'python3 /cull_idle_servers.py --cull-users --timeout=2592000 --cull-every=7620 --concurrency=1'.split(),
  },
  # Service to show stats.
  {
    'name': 'stats',
    'admin': True,
    'url': 'http://%s:36541'%os.environ['JUPYTERHUB_SVC_SERVICE_HOST'],
    'command': ['python3',
                '/srv/jupyterhub/hub_status_service.py' if os.path.exists('/srv/jupyterhub/hub_status_service.py') else '/hub_status_service.py'],
  },
]
