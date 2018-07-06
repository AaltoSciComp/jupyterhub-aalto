#!/bin/bash
set -x
username=$1
uid=$(id -u $username)

if [ -z "$uid" ] ; then
  uid="$2"
fi

dir_name=/mnt/jupyter/user/$username

#if [ ! -d $dir_name ]; then
  mkdir -p $dir_name 2>/dev/null
  chown $uid $dir_name
  chmod 700 $dir_name
#fi
