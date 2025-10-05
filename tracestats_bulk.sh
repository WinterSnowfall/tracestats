#!/bin/bash

# replace this with an absolute path if necessary
APITRACE_PATH="$(which apitrace)"
# (re)process zstd compressed traces
PROCESS_COMPRESSED=true
# only dump shaders from apitraces
DUMP_SHADERS=false

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
            if $DUMP_SHADERS
            then
                PACKED_FILENAME="$(basename "$file" .trace.zst)_dumps.tar.zst"

                if [ ! -f "dumps/$PACKED_FILENAME" ]
                then
                    ./tracestats.py -i "$file" -d -a "$APITRACE_PATH" $API_FILTER 2>&1 | tee -a tracestats_bulk.log
                    DUMPS=$(ls dumps/*.bin 2>/dev/null | wc -l)

                    if [ $DUMPS -gt 0 ]
                    then
                        cd dumps
                        tar -I "zstd -z -T0 --long -19" -cvf "$PACKED_FILENAME""_dumps.tar.zst" *.bin > /dev/null
                        rm -f *.bin
                        cd ..
                    fi
                fi
            else
                ./tracestats.py -i "$file" -a "$APITRACE_PATH" $API_FILTER 2>&1 | tee -a tracestats_bulk.log
            fi
        fi
    done
fi

for file in traces/*.trace
do
    if [ -f "$file" ]
    then
        if $DUMP_SHADERS
        then
            PACKED_FILENAME="$(basename "$file" .trace)"

            if [ ! -f "dumps/$PACKED_FILENAME" ]
            then
                ./tracestats.py -i "$file" -d -a "$APITRACE_PATH" $API_FILTER 2>&1 | tee -a tracestats_bulk.log
                DUMPS=$(ls dumps/*.bin 2>/dev/null | wc -l)

                if [ $DUMPS -gt 0 ]
                then
                    cd dumps
                    tar -I "zstd -z -T0 --long -19" -cvf "$PACKED_FILENAME""_dumps.tar.zst" *.bin > /dev/null
                    rm -f *.bin
                    cd ..
                fi
            fi
        else
            ./tracestats.py -i "$file" -a "$APITRACE_PATH" $API_FILTER 2>&1 | tee -a tracestats_bulk.log
        fi
    fi
done

