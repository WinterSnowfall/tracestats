#!/bin/bash

# replace this with an absolute path if necessary
APITRACE_PATH="$(which apitrace)"
# (re)process zstd compressed traces
PROCESS_COMPRESSED=true

if $PROCESS_COMPRESSED
then
    for file in traces/*.trace.zst
    do
        if [ -f "$file" ]
        then
            zstd -d "$file"
            ./tracestats.py -t 4 -i "${file%.zst}" -a "$APITRACE_PATH"
            rm -f "${file%.zst}"
        fi
    done
else
    for file in traces/*.trace
    do
        if [ -f "$file" ]
        then
            ./tracestats.py -t 4 -i "$file" -a "$APITRACE_PATH"
        fi
    done
fi

