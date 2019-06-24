"""Convert a csv file with a username to email address.

This uses an active directory lookup.  Before running, run 'kinit' otherwise
you won't be able to look up things.  The effect will be the script seems to
hang.

Sample usage:

Convert a single file.  Output to stdout:
  python3 username-to-email.py input.csv

Specify column 3 (note that columns are zero-indexed):
  python3 username-to-email.py input.csv --column 3

Instead of printing results to stdout, save to a file:
  python3 username-to-email.py input.csv --column 3 output.csv

If an email can't be looked up, it prints an error message to stdout and the
email field is left blank.


"""

from __future__ import print_function

import argparse
import subprocess
import re
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', nargs='?', help="File to read, default stdin")
    parser.add_argument('output', nargs='?', help="File to write, default stdout")
    parser.add_argument('--column', '-c', metavar='USERNAME_COLUMN', help='this is the column with the username (zero-indexed, default 0)', nargs='?', default=0)
    args = parser.parse_args()

    if args.output:
        output = open(args.output, 'w')
    else:
        output = sys.stdout

    usernames = [] # holds usernames read from file
    username_map = { } # map usernames to found emails

    # Read usernames to list
    lines = []
    for line in open(args.input) if args.input else sys.stdin:
        line = line.strip()
        line = line.split(',')
        username = line[int(args.column)]
        if not line:
            continue
        usernames.append(username)
        lines.append(line)

    # Make search like (|(samaccountname=name1)(samaccountname=name2))
    searches = [ (lambda x: '(samaccountname={})'.format(x))(x) for x in usernames ]
    searchexpression = "(|{})".format(''.join(searches))
    cmd = ['net', 'ads', 'search', searchexpression, 'samaccountname', 'mail']
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    
    # Capture username / email pairs    
    for line in out.decode().strip().split('\n\n')[1:]:
        username_capture = re.search('sAMAccountName: ([.a-zA-Z0-9]+)', line)
        mail_capture = re.search('mail: ([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', line)
        if (not username_capture or not mail_capture):
            continue
        username = username_capture.group(1)
        mail = mail_capture.group(1)
        username_map[username] = mail

    # Print found mails to the output file
    for line in lines:
        username = line[int(args.column)]
        if username_map.get(username, None) is not None:
            line.insert(int(args.column)+1, username_map.get(username))
            print(','.join(line), file=output)
        else:
            print("Couldn't find mail for: {}".format(username), file=sys.stderr)

main()

