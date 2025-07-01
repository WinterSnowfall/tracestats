#!/bin/bash

for file in export/*.json
do
    if [ -f "$file" ]
    then
        if [ -f "$file.bak" ]
        then
            echo "Processing file: $file"
            diff --color "$file.bak" "$file"
        fi
    fi
done

