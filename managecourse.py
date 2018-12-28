import glob
import os
from pathlib import Path
import sys
import yaml

METADIR = "/mnt/jupyter/course/meta/"        # course .yaml:s
BASEDIR = "/mnt/jupyter/course/"             # course base dir (cantais course/files)
COURSEDIR = "/mnt/jupyter/course/{slug}/files"   # course dir
DATADIR = "/mnt/jupyter/course/{slug}/coursedata/"  # course data dir (optional)
EXCHANGEDIR = "/mnt/jupyter/exchange/"

MODE_BASE     = 0o2775     # exactly equal  - /{slug}
MODE_COURSE   = 0o2770     # exactly equal  - /{slug}/files
MODE_DATA     = 0o2774     # minimum
MODE_EXCHANGE = 0o2775     # top level only

def setperm(path, perm, dirs_only=False):
    """Recursively set permissions, don't touch if OK to preserve ctime"""
    if dirs_only:    dirs_only = '! -type d'
    else:            dirs_only = ''
    ret = os.system('find %s %s ! -perm %s -exec chmod %s {} \\+'%(
        path, dirs_only, perm, perm))
def setgrp(path, gid):
    """Recursively set group, don't touch if OK to preserve ctime"""
    ret = os.system('find %s ! -group %s -exec chgrp %s {} \\+'%(
        path, gid, gid))    

class Course():
    def __init__(self, slug, data):
        self.slug = slug
        self.data = data

    # Common data
    @property
    def gid(self):  return self.data['gid']
    @property
    def uid(self):  return self.data['uid']
    @property
    def has_datadir(self): return self.data.get('datadir', False)
    @property
    def coursedir(self): return Path(BASEDIR) / self.slug
    @property
    def exchangedir(self): return Path(EXCHANGEDIR) / self.slug
    @property
    def datadir(self):
        if not self.has_datadir: return None
        return Path(BASEDIR) / self.slug

    
    def check(self):
        """Raise assertion errors if major problems detected.

        This can be run often (in fact, every time this script is run
        for any purpose) just to make sure there are no glaring
        problems, such as a course directory world readable.  It
        should be fast and make the most important checks.
        """
        # Base dir (course dir)
        assert self.coursedir.exists()
        assert self.exchangedir.exists()
        coursedir_stat = os.stat(str(self.coursedir))
        #assert coursedir_stat.st_uid == self.uid
        #assert coursedir_stat.st_gid == self.gid
        assert coursedir_stat.st_mode & MODE_BASE == MODE_BASE, "%s %o!=%o"%(self.coursedir, coursedir_stat.st_mode, MODE_BASE)

        # Data dir
        if self.has_datadir:
            assert self.datadir.exists()
            datadir_stat = os.stat(str(self.datadir))
            assert datadir_stat.st_mode & MODE_DATA == MODE_DATA

        # Exchange dir
        assert self.exchangedir.exists()
        exchangedir_stat = os.stat(str(self.exchangedir))
        assert exchangedir_stat.st_mode & MODE_EXCHANGE == MODE_EXCHANGE
        inbound = self.exchangedir/self.slug/'inbound'
        if inbound.exists():
            assert os.stat(str(inbound)).st_mode & 0o2773  #drwxrws-wx
        outbound = self.exchangedir/self.slug/'outbound'
        if outbound.exists():
            assert os.stat(str(outbound)).st_mode & 0o2775  #drwxrwsr-x

    def setup(self, force=False):
        """Idempotently set up the course, also fix some problems.

        This creates a course, data (if requested), and exchange
        directories.  It can be run at any time and should serve to
        always fix any wrong permissions that may be there.

        """
        print("Creating course %s"%self.slug)
        
        # Course dir
        self.coursedir.mkdir(exist_ok=True)
        os.chmod(str(self.coursedir), MODE_BASE)
        os.chown(str(self.coursedir), self.uid, self.gid)
        # Set perm for everything, if not correct (use find to not update ctime)
        setperm(self.coursedir, "u+rwX,g+rwX,o-rwx")
        setperm(self.coursedir, "g+s", dirs_only=True)

        # Data
        if self.has_datadir:
            self.datadir.mkdir(exist_ok=True)
            os.chmod(str(self.datadir), MODE_DATA)
            os.chown(str(self.datadir), self.uid, self.gid)
            setperm(self.datadir, "u+rwX,g+rwX,o+rX")
            setperm(self.datadir, "g+s", dirs_only=True)

        # Exchange
        self.exchangedir.mkdir(exist_ok=True)
        os.chmod(str(self.exchangedir), MODE_EXCHANGE)
        os.chown(str(self.exchangedir), self.uid, self.gid)
        setgrp(self.exchangedir, self.gid)
        if (self.exchangedir/self.slug/'inbound').exists():
            for dir_ in [self.exchangedir/self.slug/'inbound',
                         self.exchangedir/self.slug/'outbound']:
                setperm(dir_, "g+rwX")
                setperm(dir_, "g+s", dirs_only=True)
            
        setperm(self.exchangedir, "g+rwX")
        setperm(self.exchangedir, "g+s", dirs_only=True)
    

def load_courses():
    """Load all yaml files into course objects."""
    course_files = glob.glob(os.path.join(METADIR, '*.yaml'))
    courses = { }
    for course_file in course_files:
        course_slug = os.path.splitext(os.path.basename(course_file))[0]
        if course_slug.endswith('-users'):
            pass
        #course_slug = course_slug[:-6]
        course_data = yaml.load(open(course_file))
        courses[course_slug] = Course(course_slug, course_data)
    return courses

    
if __name__ == "__main__":

    import argparse
    description = """Reads all course .yaml files, and a) if a course slug is given on
    the command line, set up this course, b) In all cases, check all
    existing courses for problems and raise AssertionErrors if any are
    found, c) If a course slug is given on the command line.  """
    parser = argparse.ArgumentParser(description='Manage courses')
    
    courses = load_courses()

    if len(sys.argv) > 1:
        courses[sys.argv[1]].setup()

    for course_slug, course in sorted(courses.items()):
        print("checking", course_slug)
        course.check()
