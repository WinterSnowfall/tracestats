#!/bin/bash

for file in traces/*.trace
do
    if [ -f "$file" ]
    then
        echo "Detected uncompressed apitrace: $file"
        zstd -z -9 -T0 "$file" -o "$file.zst"
        if [ $? -eq 0 ]
        then
            rm -f "$file"
        fi
    fi
done

