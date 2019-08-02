import copy
import glob
import grp
import os
from pprint import pprint
import pwd # for resolving username --> uid
import re
import socket
import subprocess
import sys
import time
import traceback
import yaml

# c.JupyterHub.log_level = 'DEBUG'

IMAGE_DEFAULT = 'aaltoscienceit/notebook-server:1.0.0'
IMAGE_DEFAULT_R = 'aaltoscienceit/notebook-server-r-ubuntu:1.0.0'
IMAGE_DEFAULT_JULIA = 'aaltoscienceit/notebook-server-julia:1.0.0'
IMAGE_TESTING = 'aaltoscienceit/notebook-server:1.0.0'
IMAGES_OLD = [
    'aaltoscienceit/notebook-server:0.5.9',
]
DEFAULT_MEM_GUARANTEE = '.5G'
DEFAULT_CPU_GUARANTEE = .10
DEFAULT_MEM_LIMIT = '2G'
DEFAULT_CPU_LIMIT = 4
DEFAULT_TIMEOUT = 3600 * 1
DEFAULT_TIMELIMIT = 3600 * 8
INSTRUCTOR_MEM_LIMIT = DEFAULT_MEM_LIMIT
INSTRUCTOR_CPU_LIMIT = DEFAULT_CPU_LIMIT
INSTRUCTOR_MEM_GUARANTEE = '1G'
INSTRUCTOR_CPU_GUARANTEE = DEFAULT_CPU_GUARANTEE
ROOT_THEN_SU = True


DEFAULT_NODE_SELECTOR = { }
DEFAULT_TOLERATIONS = [
    {'key': 'cs-aalto/app', 'value': 'jupyter', 'operator': 'Equal', 'effect': 'NoSchedule'},
    ]
EMPTY_PROFILE = {'node_selector': DEFAULT_NODE_SELECTOR,
                 'tolerations': DEFAULT_TOLERATIONS,
                 'default_url': 'tree/notebooks'}

def unique_suffix(base, other):
    """Return the unique suffix of other, relative to base."""
    prefix = os.path.commonprefix([base, other])
    suffix = other[len(prefix):]
    if ':' not in suffix:
        suffix = other.rsplit(':', 1)[-1]
    return suffix


# Default profile list
PROFILE_LIST_DEFAULT = [
    {'display_name': 'Python: General use (JupyterLab) '
                      '<font color="#999999">%s</font>'%(IMAGE_DEFAULT.split(':')[-1]),
     'default': True,
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True, },
    },
    {'display_name': 'Python: General use (classic notebook) '
                     '<font color="#999999">%s</font>'%(IMAGE_DEFAULT.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': ''},
    },
    {'display_name': 'R: General use (JupyterLab) '
                     '<font color="#999999">%s</font>'%(IMAGE_DEFAULT_R.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True,
                               'image': IMAGE_DEFAULT_R, },
    },
    {'display_name': 'Julia: General use (JupyterLab) '
                     '<font color="#999999">%s</font>'%(IMAGE_DEFAULT_JULIA.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True,
                               'image': IMAGE_DEFAULT_JULIA,
                               'node_selector':{'kubernetes.io/hostname': 'jupyter-k8s-node2.cs.aalto.fi'},},
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
                      '<font color="#999999">%s</font>'%(IMAGE_DEFAULT.split(':')[-1]),
     'kubespawner_override': {**EMPTY_PROFILE, 'course_slug': '', 'x_jupyter_enable_lab': True,
                              'image':IMAGE_DEFAULT, 'xx_name': 'gpu_testing',
                              'node_selector':{'kubernetes.io/hostname': 'k8s-gpu-test.cs.aalto.fi'},
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
c.Authenticator.admin_users = {'darstr1', }
USER_RE = re.compile('^[a-z0-9.]+$')


# Spawner config
c.JupyterHub.spawner_class = 'kubespawner.KubeSpawner'
c.KubeSpawner.start_timeout = 60 * 5
c.KubeSpawner.hub_connect_port = 8081
c.KubeSpawner.http_timeout = 60 * 5
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
  {"name": "user",
   "nfs": {"server": "jhnas.org.aalto.fi", "path": "/vol/jupyter/u/{uid_last2digits}/{username}"}},  #{uid_last2digits}
  {"name": "shareddata",
   "nfs": {"server": "jhnas.org.aalto.fi", "path": "/vol/jupyter/shareddata/"}},
]
DEFAULT_VOLUME_MOUNTS = [
  {"mountPath": "/notebooks", "name": "user"},
  {"mountPath": "/mnt/jupyter/shareddata", "name": "shareddata", "readOnly":False},
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

    # Regenerate the course dict from yamls on disk.
    #c.JupyterHub.log.debug("Re-generating course data")
    COURSES_TS = time.time()
    courses = { }
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
            except KeyError:
                print("ERROR: group {} can not look up group info".format(course_slug), file=sys.stderr)

    # Set global variable from new local variable.
    COURSES = courses
    return COURSES
# Run it once to set the course data at startup.
GET_COURSES()


def get_profile_list(spawner):
    """gerenate the k8s profile_list.
    """
    #c.JupyterHub.log.debug("Recreating profile list")
    # All courses
    profile_list = [ ]
    for course_slug, course_data in GET_COURSES().items():
        is_student = spawner.user.name in course_data.get('students', [])
        is_instructor = spawner.user.name in course_data.get('instructors', [])
        is_teststudent = spawner.user.name in {'student1', 'student2', 'student3'}
        is_admin = spawner.user.admin
        is_active = course_data.get('active', True)
        is_private = course_data.get('private', False)
        course_notes = ""
        if not is_active:
            continue
        if is_private:
            if not (is_instructor or is_student or is_teststudent or is_admin):
                continue
            if not is_student:
                course_notes = ' <font color="brown">(not public)</font>'
        display_name = course_data.get('name', course_slug)
        profile_list.append({
            'display_name': display_name + course_notes,
            'kubespawner_override': {
                **EMPTY_PROFILE,
                'course_slug': course_slug,
                **course_data.get('kubespawner_override', {}),
                },
            'x_jupyter_enable_lab': False,
            })
        if 'image' in course_data:
            profile = profile_list[-1]   # REFERENCE
            profile['display_name'] = profile['display_name'] + ' <font color="#999999">' + unique_suffix(IMAGE_DEFAULT, course_data['image'])+'</font>'
            profile['kubespawner_override']['image'] = course_data['image']
        if is_instructor:
            profile = copy.deepcopy(profile_list[-1])  # COPY AND RE-APPEND
            profile['display_name'] = display_name + ' <font color="blue">(instructor)</font>'
            if 'image_instructor' in course_data:
                profile['display_name'] = profile['display_name'] + ' <font color="#999999">' + unique_suffix(IMAGE_DEFAULT, course_data['image_instructor'])+'</font>'
                profile['kubespawner_override']['image'] = course_data['image_instructor']
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




def create_user_dir(username, uid, log=None):
    # create_user_dir.sh knows how to compete directory from (uid, username)
    #os.system('ssh jupyter-k8s-admin.cs.aalto.fi "/root/jupyterhub/scripts/create_user_dir.sh {0} {1}"'.format(username, uid))
    ret = subprocess.run(
        'ssh jupyter-manager.cs.aalto.fi "/root/jupyterhub/scripts/create_user_dir.sh {0} {1}"'.format(username, uid),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
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

    # Get basic info
    username = spawner.user.name
    if not USER_RE.match(username):
        raise RuntimeError("Invalid username: %s, logout and use lowercase Aalto username."%username)
    userinfo = pwd.getpwnam(username)
    homedir = userinfo.pw_dir
    if homedir.startswith('/u/'): homedir = homedir[3:]
    uid = userinfo.pw_uid
    uid_last2digits = "%02d"%(uid%100)
    spawner.log.info("pre_spawn_hook: %s starting %s", username, getattr(spawner, 'course_slug', 'None'))


    # Make a copy of the *default* class volumes.  The "spawner" object
    # is constantly reused.
    spawner.volumes = copy.deepcopy(DEFAULT_VOLUMES)
    spawner.volume_mounts = copy.deepcopy(DEFAULT_VOLUME_MOUNTS)
    assert spawner.volumes[0]['name'] == 'user'
    #print(spawner.volumes, file=sys.stderr)
    spawner.volumes[0]['nfs']['path'] = spawner.volumes[0]['nfs']['path'].format(username=username, uid_last2digits=uid_last2digits)
    #print(spawner.volumes, file=sys.stderr)

    # Set basic spawner properties
    #storage_capacity = ???
    spawner.environment = environ = { }  # override env
    environ['AALTO_JUPYTERHUB'] = '1'
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

    create_user_dir(username, uid, log=spawner.log)
    #cmds.append(r'echo "if [ \"\$SHLVL\" = 1 -a \"\$PWD\" = \"\$HOME\" ] ; then cd /notebooks ; fi" >> /home/jovyan/.profile')
    cmds.append(r'echo "if [ \"\$SHLVL\" = 1 -a \( \"\$PWD\" = \"\$HOME\" -o \"\$PWD\" = / \)  ] ; then cd /notebooks ; fi" >> /home/jovyan/.bashrc')

    #for line in ['[user]',
    #             '    name = {}'.format(fullname),
    #             '    email = {}'.format(email),
    #             ]:
    #    cmds.append(r"echo '{}' >> /home/jovyan/.gitconfig".format(line))
    #    cmds.append("fix-permissions /home/jovyan/.gitconfig")

    course_slug = getattr(spawner, 'course_slug', '')
    # We are not part of a course, so do only generic stuff
    # if gid is None, we have a course definition but no course data (only setting image)
    if not course_slug or GET_COURSES()[course_slug]['gid'] is None:
        cmds.append("disable_formgrader.sh")
        # The pod_name must always be set, otherwise it uses the last pod name.
        spawner.pod_name = 'jupyter-{}{}'.format(username, '-'+spawner.name if spawner.name else '')

    # Course configuration - only if it is a course
    else:
        spawner.log.debug("pre_spawn_hook: course %s", course_slug)
        course_data = GET_COURSES()[course_slug]
        spawner.pod_name = 'jupyter-{}-{}{}'.format(username, course_slug, '-'+spawner.name if spawner.name else '')
        if getattr(course_data, 'jupyterlab', False):
            environ['JUPYTER_ENABLE_LAB'] = 'true'
            spawner.default_url = "lab/tree/notebooks/"

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
        # Add coursedata dir, if it exists
        if course_data.get('datadir', False):
            spawner.volumes.append({
                "name": "coursedata",
                "nfs": {
                    "server": "jhnas.org.aalto.fi",
                    "path": "/vol/jupyter/course/{}/data/".format(course_slug)
                }
            })
            spawner.volume_mounts.append({"mountPath": "/coursedata",
                                          "name": "coursedata",
                                          "readOnly": username not in course_data.get('instructors', {})})


        # Jupyter/nbgrader config
        for line in ['c = get_config()',
                     'c.CourseDirectory.root = "/course"',
                     'c.CourseDirectory.groupshared = True',
                     'c.CourseDirectory.course_id = "{}"'.format(course_slug),
                     'c.Exchange.course_id = "{}"'.format(course_slug),
                     'c.CourseDirectory.ignore = [".ipynb_checkpoints", "*.pyc*", "__pycache__", "feedback", ".*"]',
                     'c.CourseDirectory.max_size = 2*1024*(1024/1000.)',
                     'c.Exchange.assignment_dir = "/notebooks/"',
                     'c.Exchange.timezone = "Europe/Helsinki"',
                     'c.NbGraderAPI.timezone = "Europe/Helsinki"',
                     'c.AssignmentList.assignment_dir = "/notebooks/"',
                     'c.ExecutePreprocessor.timeout = 240',
                     'c.Execute.timeout = 240',
                     'c.Exchange.path_includes_course = True',
                     'c.Validator.validate_all = True',
                     'c.CollectApp.check_owner = False',
                     *course_data.get('nbgrader_config', '').split('\n'),
                     ]:
            cmds.append(r"echo '{}' >> /etc/jupyter/nbgrader_config.py".format(line))
        for line in ['c.AssignmentList.assignment_dir = "/notebooks/"',
                     'c.ExecutePreprocessor.timeout = 240',
                     'c.Execute.timeout = 240',
                     ]:
            cmds.append(r"echo '{}' >> /etc/jupyter/jupyter_notebook_config.py".format(line))

        # Instructors
        allow_spawn = False
        if username in course_data.get('instructors', {}):
            allow_spawn = True
        if username in course_data.get('instructors', {}) and getattr(spawner, 'as_instructor', False):
            spawner.log.info("pre_spawn_hook: User %s is an instructor for %s", username, course_slug)
            allow_spawn = True
            # Instructors get the whole filesystem tree, because they
            # need to be able to access "/course", too.  Warning, you
            # will have different paths!  (fix later...)
            #spawner.cpu_limit = 1
            spawner.mem_limit = INSTRUCTOR_MEM_LIMIT
            spawner.cpu_guarantee = INSTRUCTOR_CPU_GUARANTEE
            spawner.mem_guarantee = INSTRUCTOR_MEM_GUARANTEE
            for line in ['c.NbGrader.logfile = "/course/.nbgraber.log"',
                        ]:
                cmds.append(r"echo '{}' >> /etc/jupyter/nbgrader_config.py".format(line))
            spawner.volumes.append({
                "name": "course",
                "nfs": {
                    "server": "jhnas.org.aalto.fi",
                    "path": "/vol/jupyter/course/{}/files".format(course_slug)
                }
            })
            spawner.volume_mounts.append({ "mountPath": "/course", "name": "course" })
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

    # import pprint
    # spawner.log.info("Before hooks: spawner.node_selector: %s", spawner.node_selector)

    # User- and course-specific hooks
    hook_file = '/srv/jupyterhub/hooks-user/{}.py'.format(username)
    if os.path.exists(hook_file):
        spawner.log.info("pre_spawn_hook: Running %s", hook_file)
        exec(open(hook_file).read())
    hook_file = '/srv/jupyterhub/hooks-course/{}.py'.format(course_slug)
    if course_slug and os.path.exists(hook_file):
        spawner.log.info("pre_spawn_hook: Running %s", hook_file)
        exec(open(hook_file).read())

    # import pprint
    # spawner.log.info("After hooks: spawner.node_selector: %s", spawner.node_selector)
    # spawner.log.info("After hooks: spawner.__dict__: %s", pprint.pformat(spawner.__dict__))

    # Common final setup
    #pprint(vars(spawner), stream=sys.stderr)
    #pprint(spawner.volumes, stream=sys.stderr)
    for var in ['OMP_NUM_THREADS',
                'OPENBLAS_NUM_THREADS',
                'NUMEXPR_NUM_THREADS',
                'MKL_NUM_THREADS', ]:
        environ[var] = str(int(spawner.cpu_limit))
    cmds.append("source start-notebook.sh")   # args added later in KubeSpawner
    spawner.cmd = ["bash", "-x", "-c", ] + [" && ".join(cmds)]


def post_stop_hook(spawner):
    username = spawner.user.name
    course_slug = getattr(spawner, 'course_slug', '')
    spawner.log.info("post_stop_hook: %s stopped %s", username, course_slug or 'None')


c.KubeSpawner.pre_spawn_hook = pre_spawn_hook
c.KubeSpawner.post_stop_hook = post_stop_hook


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

