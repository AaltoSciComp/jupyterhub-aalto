#!/usr/bin/bash

if [[ ${SKIP_PROMPT:-no} != yes ]]; then
  if [[ $NAMESPACE == jupyter ]] || [[ $NAMESPACE == jupyter2 ]]; then
    echo -n "Do you want to run $(basename "$0") in the PRODUCTION ENVIRONMENT? ($NAMESPACE) [y/N]: "
    read -r agree
    if [[ $agree != y ]]; then
      echo "Exiting"
      exit
    fi
    echo "Continuing"
    export SKIP_PROMPT=yes
  else
    echo "Namespace: $NAMESPACE"
  fi
fi
