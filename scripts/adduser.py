#!/usr/bin/python3

import os
import re
import sys

USERHOME='/srv/jupyter-tw/user/'

user = sys.argv[1]
print("Creating user dirs:", user)

if not re.match('^[a-z0-9]+$', user):
    raise ValueError("Invalid username: {}".format(user))

home = user
uid = 1000

home = os.path.join(USERHOME, home)
os.makedirs(home, mode=0o700, exist_ok=True)
print("User directory created:", home)
