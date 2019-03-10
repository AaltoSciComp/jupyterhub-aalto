import glob
import os
from pathlib import Path
import re
import sys
import yaml
import subprocess

BASE = '/mnt/jupyter/'
COURSEDIR = BASE+'course/{slug}/files/'
USERDIR = BASE+'u/{digits}/{username}/'
USERINFO = BASE+'admin/lastlogin/{username}'
USER_GID = 70000

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Send feedback to students')
    parser.add_argument('--assignment', '-a', help='limit to assignment ID')
    parser.add_argument('course', help='course(s) to give feedback for')
    parser.add_argument('username', nargs='*', help='usernames')
    args = parser.parse_args()

    if args.assignment:
        assignment = args.assignment
    else:
        assignment = ''

    
    # Find all the user directories
    userdirs = { }
    userdir_re = re.compile(USERDIR.format(digits='([0-9]{2})', username='([^/]+)'))
    for path in glob.glob(USERDIR.format(digits='*', username='*')):
        m = userdir_re.match(path)
        userdirs[m.group(2)] = USERDIR.format(digits=m.group(1), username=m.group(2))
        #print(m.group(1), m.group(2))

    # Find our users
    course_slug = args.course
    print(course_slug, COURSEDIR.format(slug=course_slug)+'feedback/*')
    user_paths = glob.glob(COURSEDIR.format(slug=course_slug)+'feedback/*')
    #print(course_assignments)

    for user_source_path in user_paths:
        m = re.match('.*/([^/]+)$', user_source_path)
        username = m.group(1)
        if args.username and username not in args.username:
            continue
        print(user_source_path)
        data = yaml.load(open(USERINFO.format(username=username))) or { }
        uid = data.get('uid', 0)
        print(username, uid)

        user_source = Path(user_source_path)

        # If we have limited to one assignment, and it doesn't exist
        # in the user source, don't do anything.
        if assignment and not (user_source/args.assignment).exists():
            continue
        assignment_limit = [ ]
        if assignment:
            assignment_limit = ['--include', assignment+'***', '--exclude', '*']

        cmd = ['rsync', '-r', '--update', 
               '-og', '--chown=%s:%s'%(uid, USER_GID),
               '--perms', '--chmod=u+rwX,g=,g-s,o=',
               *assignment_limit,
               str(user_source)+'/',
               str(Path(USERDIR.format(digits='%02d'%(uid%100), username=username))/course_slug/'feedback')+'/',
                ]
        print(cmd)
        #subprocess.call(cmd)

main()
