# Gmail Setup

######## Features ########

Without force download, each email will be downloaded only once, its message id is logged in a file after the first successful download

######## Usage ########

--- creating credentials ---
Open the Google Cloud Console @ <https://console.cloud.google.com/>
At the top-left, click Menu menu > APIs & Services > Credentials.
Click Create Credentials > oauth client ID.
Click Application type > Desktop app.
In the "Name" field, type a name for the credential. This name is only shown in the Cloud Console.
Click Create. The oauth client created screen appears, showing your new Client ID and Client secret.
Click OK. The newly created credential appears under "oauth 2.0 Client IDs."
Save in an auth_dir specefic to the account you are using
on the app screen go to oauth consent screen, next until you hit scopes, and add gmail.compose and or gmail.readonly depending on scope of project

--- downloading existing credentials ---
Open the Google Cloud Console @ <https://console.cloud.google.com/>
At the top-left, click Menu menu > APIs & Services > Credentials.
Click oauth client ID > Select the client ID you created.
Click Download JSON.
Save in an auth_dir specefic to the account you are using
on the app screen go to oauth consent screen, next until you hit scopes, and add gmail.compose and or gmail.readonly depending on scope of project

--- to import ---
from utils.gmail_tools import get_attachment_from_search_string

---search_string---
set gmail search string, can use todays date but must be a string or f string

---output_path---
use os.path.join on your path to make sure it is correct

---output_file_name---
set output_file_name to None if you want to use the original file name
set output_file_name to 'original with date' if you want to use the original file name with date

---force_download---
set force_download to True if you want to download the file even if it has already been downloaded

---retries---
Set retry variable if inconsistant results, default is 3, will not duplicate files or keep trying if it succeeds

######## Limitations ########

Only downloads first file in the attachments of each email
