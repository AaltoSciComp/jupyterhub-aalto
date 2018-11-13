#!/bin/bash

set -e  # exit immediately on any command failing
set -x  # debugging

# Place this in ssh/authorised_keys with this key:
#   restrict,command="bash path/to/this.sh" ssh-rsa ...
if [ -n "$SSH_ORIGINAL_COMMAND" ] ; then
    set -- $SSH_ORIGINAL_COMMAND
    original_cmd="$1"
    shift
else
    # Change to false to *require* command=.
    true
fi


echo "$@"

# validate username
username="$1"
if echo "$username" | egrep -v '^[a-z0-9.]+$' ; then
    echo "ERROR: bad username"
    exit 2
fi

touch "/mnt/jupyter/admin/lastlogin/$username"

# Get uid from PAM, but if that fails then use the supplied uid (for
# local users).
set +e
uid=$(id -u $username)
if [ -z "$uid" ] ; then
  uid="$2"
fi
set -e

uid_last2digits=$(printf %02d $(($uid % 100)) )
dir_name="/mnt/jupyter/u/$uid_last2digits/$username"
default_group=70000

#if [ ! -d "$dir_name" ]; then
  mkdir --mode 0700 -p "$dir_name"
  chown "$uid:$default_group" "$dir_name"
  chmod 700 "$dir_name"
#fi
