#!/bin/bash

set -e  # exit immediately on any command failing
set -x  # debugging

JUPYTER_DIR=/mnt/jupyter
LASTLOGIN_DIR="$JUPYTER_DIR/admin/lastlogin"

# NOTE: The value doesn't seem to have actually ever been used
# # Place this in ssh/authorised_keys with this key:
# #   restrict,command="bash path/to/this.sh" ssh-rsa ...
# if [ -n "$SSH_ORIGINAL_COMMAND" ] ; then
#     set -- "$SSH_ORIGINAL_COMMAND"
#     original_cmd="$1"
#     shift
# else
#     # Change to false to *require* command=.
#     true
# fi


echo "$@"

# validate username
username="$1"
if echo "$username" | grep -E -v '^[a-z0-9.]+$' ; then
    echo "ERROR: bad username"
    exit 2
fi

# Get uid from PAM, but if that fails then use the supplied uid (for
# local users).
uid="$(id -u "$username" || true)"
if [ -z "$uid" ] ; then
  uid="$2"
fi

mkdir -p "$LASTLOGIN_DIR"
touch "$LASTLOGIN_DIR/$username"
echo "uid: $uid" > "$LASTLOGIN_DIR/$username"
echo "ts: $(date +%s)" >> "$LASTLOGIN_DIR/$username"
echo "human_name: \"$3\"" >> "$LASTLOGIN_DIR/$username"

uid_last2digits=$(printf %02d $((uid % 100)) )
dir_name="$JUPYTER_DIR/u/$uid_last2digits/$username"
default_group=70000

#if [ ! -d "$dir_name" ]; then
  mkdir -p "$dir_name"
  chown "$uid:$default_group" "$dir_name"
  chmod 700 "$dir_name"
#fi
