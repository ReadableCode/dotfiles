#!/bin/bash
# Started at login by ~/.config/autostart/start_x0vncserver.desktop, which the
# deploy manifest links here (entry vnc_autostart_desktop). See
# docs/setup_vnc_server.md.
printf '%.0s#' {1..100} >> "$HOME/x0vncserver.log"
echo $(date) >> "$HOME/x0vncserver.log"
/usr/bin/x0vncserver -passwordfile "$HOME/.vnc/passwd" -display :0 >> "$HOME/x0vncserver.log" 2>&1 &
echo $! > "$HOME/x0vncserver.pid"
exit 0
