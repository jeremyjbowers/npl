#!/bin/bash

while [ 1 ]; 
do
    # start time
    date +"%H:%M:%S"

    time django-admin reload

    # end time
    date +"%H:%M:%S"

    sleep 3600
done