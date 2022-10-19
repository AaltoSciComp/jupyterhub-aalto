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
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='limit to assignment ID')
    #parser.add_argument('--list', '-l', action='store_true',
    #                    help="List assignments, don't do anything else")
    parser.add_argument('--user', '-u', action='append',
                        help=('limit to these usernames (comma separated list, '
                              'or can be given multiple times)'))
    parser.add_argument('--user-exclude', action='append',
                        help=('Exclude these usernames.'))
    parser.add_argument('--feedback_dir_format', type=int, default=2,
                        help="Format to place feedback in with user directories.  1=custom, 2=nbgrader built-in.")
    parser.add_argument('course', help='course(s) to give feedback for')
    parser.add_argument('assignment', nargs='*', help='Limit to these assignment IDs')
    args = parser.parse_args()

    if args.user:
        users = set()
        for users_ in args.user:
            users.update(set(users_.split(',')))
    else:
        users = None

    if args.user_exclude:
        users_exclude = set()
        for users_ in args.user_exclude:
            users_exclude.update(set(users_.split(',')))
    else:
         users_exclude = None



    if args.assignment:
        assignments = args.assignment
    else:
        assignments = None

    # Find all the user directories.  Map username -> NN/username
    userdirs = { }
    userdir_re = re.compile(USERDIR.format(digits='([0-9]{2})', username='([^/]+)'))
    for path in glob.glob(USERDIR.format(digits='*', username='*')):
        m = userdir_re.match(path)
        userdirs[m.group(2)] = USERDIR.format(digits=m.group(1), username=m.group(2))
        #print(m.group(1), m.group(2))

    # List *all* user feedback dirs matching $course/feedback/$username
    course_slug = args.course
    print(course_slug, COURSEDIR.format(slug=course_slug)+'feedback/*')
    user_paths = glob.glob(COURSEDIR.format(slug=course_slug)+'feedback/*')
    #print(course_assignments)

    # For each {coursedir}/feedback/{assignment}
    for user_source_path in user_paths:
        # Find username
        m = re.match('.*/([^/]+)$', user_source_path)
        username = m.group(1)
        # Skip completely unknown users
        if users and username not in users:
            continue
        if users_exclude and username in users_exclude:
            continue
        # Find the user's uid
        print(user_source_path)
        data = yaml.load(open(USERINFO.format(username=username))) or { }
        uid = data.get('uid', 0)
        print(username, uid)

        user_source = Path(user_source_path)

        # For each assignment
        # Find the timestamp
        # release the feedback

        # BELOW DOESN'T APPLY WITH NEW FORMAT

        # If we have limited to one assignment, and it doesn't exist
        # in the user source, don't do anything.
        if args.feedback_dir_format == 1:
            assignment_limit = [ ]
            if assignments:
                for assignment in assignments:
                    if not (user_source/assignment).exists():
                        continue
                    assignment_limit.extend(['--include', assignment+'***',])
                assignment_limit.extend(['--exclude', '*'])

            cmd = ['rsync', '-r', '--update', '-i'+('n' if args.dry_run else ''),
                   '-og', '--chown=%s:%s'%(uid, USER_GID),
                   '--perms', '--chmod=u+rwX,g=,g-s,o=',
                   *assignment_limit,
                   str(user_source)+'/',
                   str(Path(USERDIR.format(digits='%02d'%(uid%100), username=username))/course_slug/'feedback')+'/',
                    ]
            print(cmd)
            subprocess.call(cmd)

        elif args.feedback_dir_format == 2:
            for assignment_dir in glob.glob(str(user_source/'*')):
                assignment_dir = Path(assignment_dir)
                assignment_id = assignment_dir.parts[-1]
                print(assignment_id)
                if assignments and assignment_id not in assignments:
                    print("Skipping", assignment_id)
                timestamp = open(str(assignment_dir/'timestamp.txt')).read().strip().replace('/', '')
                destination = Path(USERDIR.format(digits='%02d'%(uid%100), username=username))/course_slug/assignment_id/'feedback'/timestamp
                # Create parent directory (since {assignment}/feedback
                # will usually not be created yet).
                if not destination.parent.exists():
                    print("mkdir", destination.parent)
                    print("chown", "%s:%s"%(uid,USER_GID), destination.parent)
                    if not args.dry_run:
                        os.mkdir(str(destination.parent))
                        os.chown(str(destination.parent), uid, USER_GID)

                # Do actual copy
                cmd = ['rsync', '-r', '--update', '-i'+('n' if args.dry_run else ''),
                       '-og', '--chown=%s:%s'%(uid, USER_GID),
                       '--perms', '--chmod=u+rwX,g=,g-s,o=',
                       str(assignment_dir)+'/',
                       str(destination)+'/',
                      ]
            print(cmd)
            subprocess.call(cmd)




        else:
            raise RuntimeError("unknown feedback dir format: %s"%args.feedback_dir_format)

main()
