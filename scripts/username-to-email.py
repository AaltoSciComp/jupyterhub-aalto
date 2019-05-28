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

cache = { }
def lookup(username):
    if username in cache:
        return cache[username]
    cmd = ['net', 'ads', 'search', 'samAccountName=%s'%username, 'mail']
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    m = re.search('mail: ([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', out.decode())
    if not m:
        print('can not find mail for: %s'%username, file=sys.stderr)
        return ''
    email = m.group(1)
    cache[username] = email
    return email

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

    for line in open(args.input) if args.input else sys.stdin:
        line = line.strip()
        line = line.split(',')
        username = line[int(args.column)]
        if not line:
            continue
        email = lookup(username)
        line.insert(int(args.column)+1, email)
        print(','.join(line), file=output)

main()
