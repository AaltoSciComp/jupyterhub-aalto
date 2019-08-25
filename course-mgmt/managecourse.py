import glob
import os
from pathlib import Path
import sys
import yaml

METADIR = "/mnt/jupyter/course/meta/"            # course .yaml:s
COURSEBASEDIR = "/mnt/jupyter/course/{slug}"     # course base dir (contains course/data dirs)
COURSEDIR = "/mnt/jupyter/course/{slug}/files/"  # course dir
DATADIR = "/mnt/jupyter/course/{slug}/data/"     # course data dir (optional)
EXCHANGEDIR = "/mnt/jupyter/exchange/"

MODE_BASE     = 0o0755     # exactly equal  - /{slug}
MODE_COURSE   = 0o2770     # exactly equal  - /{slug}/files
MODE_DATA     = 0o2775     # minimum
MODE_EXCHANGE = 0o2775     # top level only

def setperm(path, perm, dirs_only=False):
    """Recursively set permissions, don't touch if OK to preserve ctime"""
    if dirs_only:    dirs_only = '-type d'
    else:            dirs_only = ''
    ret = os.system('find %s %s ! -perm %s -exec chmod %s {} \\+'%(
        path, dirs_only, perm, perm))
def setgrp(path, gid):
    """Recursively set group, don't touch if OK to preserve ctime"""
    ret = os.system('find %s ! -group %s -exec chgrp %s {} \\+'%(
        path, gid, gid))

def assert_stat(path, mode, match='exact', missing_ok=False, mask=0o7777):
    assert path.exists() or missing_ok, "Path %s is missing"%path
    stat_result = os.stat(str(path)).st_mode
    if match == 'any':
        assert stat_result & mask, "%s %o! .(any). %o (mask %o)"%(path, stat_result, mode, mask)
    else:
        # Exact match mode
        #print("%o"%stat_result)
        #print("%o"%mode)
        #print("%o"%(stat_result & mask))
        #print("%o"%((stat_result & mask) == mode))
        assert stat_result & mask == mode, "%s %o!=%o (mask %o)"%(path, stat_result, mode, mask)


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
    def coursebasedir(self): return Path(COURSEBASEDIR.format(slug=self.slug))
    @property
    def coursedir(self): return Path(COURSEDIR.format(slug=self.slug))
    @property
    def exchangedir(self): return Path(EXCHANGEDIR) / self.slug
    @property
    def datadir(self):
        if not self.has_datadir: return None
        return Path(DATADIR.format(slug=self.slug))


    def check(self):
        """Raise assertion errors if major problems detected.

        This can be run often (in fact, every time this script is run
        for any purpose) just to make sure there are no glaring
        problems, such as a course directory world readable.  It
        should be fast and make the most important checks.
        """
        # if gid is None, that means there is no course data directory
        # and we should never do anything.
        if self.gid is None:
            assert not self.coursebasedir.exists(), self.slug
            assert not self.exchangedir.exists(), self.slug
            return

        # Base dir
        assert self.coursebasedir.exists(), self.slug
        assert_stat(self.coursebasedir, MODE_BASE)

        # Course dir (course dir)
        assert self.coursedir.exists(), self.slug
        #assert coursedir_stat.st_uid == self.uid
        #assert coursedir_stat.st_gid == self.gid
        assert_stat(self.coursedir, MODE_COURSE)

        # Data dir
        if self.has_datadir:
            assert self.datadir.exists()
            assert_stat(self.datadir, MODE_DATA)
            os.system('find {} -perm /u=s,o=w -ls'.format(self.datadir))
        else:
            if Path(DATADIR.format(slug=self.slug)).exists():
                print("Warning: {} has a datadir but should'n...".format(slug))

        # Exchange dir
        assert self.exchangedir.exists()
        assert_stat(self.exchangedir, MODE_EXCHANGE)
        inbound = self.exchangedir/self.slug/'inbound'
        if inbound.exists():
            pass
            #assert_stat(inbound, 0o773, mask=0o773)
            #assert inbound_stat & 0o773, "%s %o!=%o"%(self.exchangedir+'-inbound', datadir_stat.st_mode, MODE_DATA)  #drwxrws-wx
        outbound = self.exchangedir/self.slug/'outbound'
        if outbound.exists():
            pass
            #assert os.stat(str(outbound)).st_mode & 0o2775, "%s %o!=%o"%(self.datadir+'-outbound', datadir_stat.st_mode, MODE_DATA)  #drwxrwsr-x

    def setup(self):
        """Idempotently set up the course, also fix some problems.

        This creates a course, data (if requested), and exchange
        directories.  It can be run at any time and should serve to
        always fix any wrong permissions that may be there.

        """
        print("Creating course %s"%self.slug)
        # if gid is None, that means there is no course data directory
        # and we should never do anything.
        if self.gid is None:
            print("Course gid is None, which means we do not create anything.")
            return

        # Parent holder directory
        self.coursebasedir.mkdir(exist_ok=True)
        os.chmod(str(self.coursebasedir), MODE_BASE)

        # Course dir
        self.coursedir.mkdir(exist_ok=True)
        os.chmod(str(self.coursedir), MODE_COURSE)
        os.chown(str(self.coursedir), self.uid, self.gid)
        # Set perm for everything, if not correct (use find to not update ctime)
        setperm(self.coursedir, "u+rwX,g+rwX,o-rwx")
        setperm(self.coursedir, "g+s", dirs_only=True)

        # Data
        if self.has_datadir:
            self.datadir.mkdir(exist_ok=True)
            os.chmod(str(self.datadir), MODE_DATA)
            os.chown(str(self.datadir), self.uid, self.gid)
            setperm(self.datadir, "u+rwX,g+rwX,o+rX,o-w")
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
    parser.add_argument('course', nargs='*', help='course(s) to set up')
    parser.add_argument('--check', '-c', action='store_true', help='only check courses')
    args = parser.parse_args()
    courses = load_courses()

    if args.course:
        # Deal with only specific courses
        for course in args.course:
            if args.check:
                courses[course].check()
            else:
                # Default: set up course
                print("Setting up %s"%course)
                courses[course].setup()
                courses[course].check()
    else:
        # Default if nothing specified: check everything
        for course_slug, course in sorted(courses.items()):
            print("checking all courses for problems", course_slug)
            course.check()
