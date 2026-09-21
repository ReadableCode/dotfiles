#!/bin/bash
# Started at login by ~/.config/autostart/start_x0vncserver.desktop, which the
# deploy manifest links here (entry vnc_autostart_desktop). See
# docs/setup_vnc_server.md.
printf '%.0s#' {1..100} >> "$HOME/x0vncserver.log"
echo $(date) >> "$HOME/x0vncserver.log"
# -localhost=0 is explicit because the default CHANGED between tigervnc
# releases: 1.12 binds 0.0.0.0, 1.15 binds 127.0.0.1 only. Relying on the
# default means an OS upgrade silently turns remote VNC off while the server
# still looks perfectly healthy in its log. Note the "=0" form: "-localhost no"
# is not valid syntax for x0vncserver.
/usr/bin/x0vncserver -passwordfile "$HOME/.vnc/passwd" -display :0 -localhost=0 \
    >> "$HOME/x0vncserver.log" 2>&1 &
echo $! > "$HOME/x0vncserver.pid"
exit 0
