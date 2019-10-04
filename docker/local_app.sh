#!/bin/bash
bin/dev-servers development.ini --app-name app --clear --init --load &
PID_1=$!
sleep 10
bin/pserve development.ini &
PID_2=$!

# See https://docs.docker.com/config/containers/multi-service_container/
while sleep 30; do
  # Grep for the PID, exclude the grep process itself, return 0 if found else return 1
  ps aux | grep $PID_1 | grep -q -v grep
  # Capture return code of above
  PROCESS_1_STATUS=$?
  ps aux | grep $PID_2 | grep -q -v grep
  PROCESS_2_STATUS=$?
  # If the greps above find anything, they exit with 0 status
  # If they are not both 0, then something is wrong
  if [ $PROCESS_1_STATUS -ne 0 ] || [ $PROCESS_2_STATUS -ne 0 ]; then
    echo "One of the processes has already exited."
    exit 1
  fi
done
