#!/bin/bash
printf '%.0s#' {1..100} >> /home/jason/x0vncserver.log
echo $(date) >> /home/jason/x0vncserver.log
/usr/bin/x0vncserver -passwordfile /home/jason/.vnc/passwd -display :0 >> /home/jason/x0vncserver.log 2>&1 &
echo $! > /home/jason/x0vncserver.pid
exit 0
