if [[ ${SKIP_PROMPT:-no} != yes ]]; then
  if [[ $NAMESPACE == jupyter ]]; then
    echo "Do you want to run $(basename $0) in the PRODUCTION ENVIRONMENT? [y/n]: "
    read agree
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
