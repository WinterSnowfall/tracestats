#!/bin/bash

# replace this with an absolute path if necessary
APITRACE_PATH="$(which apitrace)"
# (re)process zstd compressed traces
PROCESS_COMPRESSED=true

# API filter
if [ $# -ge 1 ]
then
    API_FILTER="-s $1"
else
    API_FILTER=""
fi

rm -f tracestats_bulk.log > /dev/null 2>&1

if $PROCESS_COMPRESSED
then
    for file in traces/*.trace.zst
    do
        if [ -f "$file" ]
        then
            ./tracestats.py -t 4 -i "$file" -a "$APITRACE_PATH" $API_FILTER 2>&1 | tee -a tracestats_bulk.log
        fi
    done
fi

for file in traces/*.trace
do
    if [ -f "$file" ]
    then
        ./tracestats.py -t 4 -i "$file" -a "$APITRACE_PATH" $API_FILTER 2>&1 | tee -a tracestats_bulk.log
    fi
done

