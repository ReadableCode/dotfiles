I would advise starting with the directions listed on the Amazon page for this display, if that fails you can also check their GitHub page.

Driver installation:

Step 1: install the Raspbian official image file:
1. Download the latest Raspbian image file from official
2. Use SDFormatter to format Micro SD card
3.Use Win32DiskImager to burn the official image to Micro SD Card

Step 2: Connect the screen with Raspberry Pi

Step 3: Install the Driver to Raspberry Pi
1.Prepare keyboard and mouse for Pi , connect internet.
2.Execute the following commands
sudo rm -rf LCD-show
git clone https://github.com/goodtft/LCD-show.git
chmod -R 755 LCD-show
cd LCD-show/
sudo ./MHS35-show

If you have difficult in installing the driver, or if you still can’t use the display properly after installing the driver, please try our pre-install driver image for testing.

For Raspberry Pi 3 B/B+, Pi Zero/W
RetroPie game system: https://drive.google.com/open?id=1KQpI3sJ6l3NNQTEruPT83050_Sl4IDsi

For Raspberry Pi 3 B/B+
Raspbian: https://drive.google.com/open?id=1rQQyoNXkxVH8vcLW_tUKWsMs4fgfJacj
Kali: https://drive.google.com/open?id=1NoHoxBSIP4i8WKCJo761K_-DcYh1IZ7k

For Raspberry Pi 3 & Pi 2 (Notice: Ubuntu system can’t support Raspberry Pi 3 B+ board)
Ubuntu: https://drive.google.com/open?id=1zZRt4SCdwn1U0SYDCMxLNcFud0olY7Pi

Rotate the display Tutorial:
https://drive.google.com/open?id=1Xh-RW62XNluIBA8vyOAJroiUjY8XvOkY
dead link,
cd into directory of LCD Driver
cd ~/LCD-show
sudo ./rotate.sh 180
########################################################################
Back to hdmi


If want to show back with HDMI monitor, please execute the command:
cd LCD-show/
sudo ./LCD-hdmi
# didnt work...

#now trying amazon comment of:
cd LCD-show/
chmod 777 LCD-hdmi
sudo ./LCD-hdmi
# nope, and some say chaning resolution manually is nessessary, still not working with moms tv

trying to add ignore_lcd=1 to /boot/config.txt

all probably worked, case on pi was preventing plugging all the way in


Links:
https://www.waveshare.com/wiki/1.3inch_LCD_HAT

https://stackoverflow.com/questions/53347759/importerror-libcblas-so-3-cannot-open-shared-object-file-no-such-file-or-dire

https://stackoverflow.com/questions/8863917/importerror-no-module-named-pil

https://gideonwolfe.com/posts/security/p4wnp1/
