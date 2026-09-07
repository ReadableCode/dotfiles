# Rsync Info

-a means copy everytihng in directory
-A means extended propertie, unix based permissions, brings with it rwx privs
-X means extended permissions as well
-v verbose mode
-aAXv all of the above

--delete means if I delete something on my source directory then delete it from my backup as well, needed to make sure destination is a mirror of the source

excluding, used to exclude drives that might be mounted in home directory and you are backing up home directory, also may want to exclude cache if backing up home foler

--exclude={/home/titus/1tb/*,/home/titus/256nvme/*} is example of some exclusions from youtube tutorial @ <https://www.youtube.com/watch?v=OEfboN-Nb2s>

source first with no trailing / ?
then destination with no trailing / ?
