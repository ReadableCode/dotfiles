#!/bin/bash

while true; do
    temp=$(cat /sys/class/thermal/thermal_zone0/temp)
    temp_c=$(echo "scale=1; $temp / 1000" | bc)
    echo -ne "CPU Temperature: $temp_c °C\r"
    sleep 1
done

