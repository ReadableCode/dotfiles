^!c:: ; Press Ctrl + Alt + C to jump to VSCode
if WinExist("ahk_exe Code.exe")
    WinActivate ; Focus VSCode if it's open
else
    Run "C:\Program Files\Microsoft VS Code\Code.exe" ; Launch if not open
return