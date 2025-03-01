#!/bin/bash

# replace this with an absolute path if necessary
APITRACE_PATH="$(which apitrace)"

for file in traces/*.trace
do
    if [ -f "$file" ]
    then
        ./tracestats.py -t 4 -i "$file" -a "$APITRACE_PATH"
    fi
done

