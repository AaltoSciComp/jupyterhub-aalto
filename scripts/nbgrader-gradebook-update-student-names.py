"""Update the nbgrader DB with real names.

Update nbgrader gradebook.dbreal name (firstname/lastname) with
information from PAM.  This can not be done in real-time, but it's
done as a nigtly script with cron.  The basic data is saved in
create_user_dir.sh and the jupyterhub_config.py hook that calls it.
It is saved in the "lastlogin" directory.  This parses that info, and
puts it in the DBs.

Add this to crontab:

find /mnt/jupyter/course/ -maxdepth 3 -name gradebook.db -mtime -14 \
  -exec python3 /root/jupyterhub-aalto/scripts/nbgrader-gradebook-update-student-names.py /mnt/jupyter/admin/lastlogin/ {} \;

"""


import argparse
import os
import pathlib
import sqlite3
import yaml


parser = argparse.ArgumentParser()
parser.add_argument('userinfo_dir')
parser.add_argument('inputs', nargs='+')
parser.add_argument('--update-all', action="store_true",
                    help="If not given, only update nulls")
parser.add_argument('--dry-run', '-n', action="store_true",
                    help="Don't actually do anything")
parser.add_argument('--quiet', '-q', action="store_true",
                    help="Don't print anything unless errors")
parser.add_argument('--verbose', '-v', action="store_true",
                    help="Be extra verbose")
args = parser.parse_args()


userinfo_dir = pathlib.Path(args.userinfo_dir)

for dbfile in args.inputs:
    if not args.quiet:
        print(dbfile)
    if os.stat(dbfile).st_size == 0:
        continue
    conn = sqlite3.connect(dbfile)

    query = "SELECT id FROM student"
    if not args.update_all:
        query += (" WHERE first_name isnull and last_name isnull")
    info = conn.execute(query).fetchall()
    info = [{'username': x[0]} for x in info]
    new_info = [ ]

    # Look up the name
    for userinfo in info:
        userfile = userinfo_dir / userinfo['username']
        if not userfile.exists() or userfile.stat().st_mtime < 1574326800:
            continue
        data = yaml.safe_load(userfile.open())
        if args.verbose:
            print(userinfo['username'], data)
        if not isinstance(data, dict): continue
        if 'human_name' not in data:
            continue
        human_name = data['human_name']
        if human_name.count("'") == 1:
            # Avoid problems with invalid quoting from the first runs
            continue
        human_name = human_name.lstrip("'").rstrip("'")
        #human_name = human_name.replace("_", " ")
        human_name = human_name.replace("++", " ")
        if '/' in human_name:
            continue
        if not args.quiet:
            print(userinfo['username'].ljust(10), human_name)
        userinfo['first_name'] = ""
        userinfo['last_name'] = human_name
        new_info.append(userinfo)

    #print(new_info)
    if not args.dry_run:
        conn.executemany("UPDATE student "
                         "SET first_name=:first_name, last_name=:last_name "
                         "WHERE id=:username",
                        new_info,
                        )
        conn.commit()




