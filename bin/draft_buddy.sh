#!/bin/bash

while [ 1 ]; 
do
    # start time
    date +"%H:%M:%S"

   time django-admin draft_buddy

    # end time
    date +"%H:%M:%S"

    sleep 10
done
