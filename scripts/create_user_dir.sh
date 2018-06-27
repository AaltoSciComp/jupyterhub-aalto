#!/bin/bash
username=$1
uid=$2

dir_name=/srv/jupyter-tw/user/$username

if [ ! -d $dir_name ]; then
  mkdir $dir_name 2>/dev/null
  chown $uid $dir_name
  chmod 700 $dir_name
fi
