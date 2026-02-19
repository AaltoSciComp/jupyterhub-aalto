#!/bin/bash
set -euo pipefail
SCRIPTPATH="$( cd "$(dirname "$0")" || exit ; pwd -P )"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 JUPYTER-PATH [MANAGER-HOSTNAME]"
    exit 1
fi

JUPYTER_PATH="$1"
JMGR_HOSTNAME="${2:-root@jupyter-manager-2.cs.aalto.fi}"

timeout 2 ssh $JMGR_HOSTNAME "mkdir -p \
    $JUPYTER_PATH/admin/hubdata \
    $JUPYTER_PATH/admin/keytab \
    $JUPYTER_PATH/admin/lastlogin \
    $JUPYTER_PATH/course \
    $JUPYTER_PATH/exchange \
    $JUPYTER_PATH/shareddata \
    $JUPYTER_PATH/software \
    $JUPYTER_PATH/u \
    && \
    chmod o-rwx $JUPYTER_PATH/admin && \
    chmod 777 $JUPYTER_PATH/admin/{hubdata,keytab} && \
    if [ ! -d $JUPYTER_PATH/course/meta ]; then \
        mkdir -p $JUPYTER_PATH/course/meta && \
        git -C $JUPYTER_PATH/course/meta init; \
    fi"
