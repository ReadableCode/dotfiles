# %%
# Imports #

from __future__ import print_function

import base64
import mimetypes
import os
import os.path
import re
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import pandas as pd
from dateutil.parser import parse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# append grandparent
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_utils import file_dir, grandparent_dir
from utils.display_tools import print_logger

# %%
# Variables #

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


# %%
# Authentication #


def deploy_auth_files_from_env(account_type):
    # if gmail_token and gmail_oauth are in the environment, write them to the default auth dir
    if f"GMAIL_OAUTH_{account_type.upper()}" in os.environ:
        print_logger(f"GMAIL_OAUTH_{account_type.upper()} in environment")
        with open(
            os.path.join(grandparent_dir, f"gmail_oauth_{account_type}.json"), "w"
        ) as f:
            f.write(os.environ[f"GMAIL_OAUTH_{account_type.upper()}"])

    if f"GMAIL_TOKEN_{account_type.upper()}" in os.environ:
        print_logger(f"GMAIL_TOKEN_{account_type.upper()} in environment")
        with open(
            os.path.join(grandparent_dir, f"gmail_token_{account_type}.json"), "w"
        ) as f:
            f.write(os.environ[f"GMAIL_TOKEN_{account_type.upper()}"])


def get_gmail_service(account_type="default"):
    oauth_path = os.path.join(grandparent_dir, f"gmail_oauth_{account_type}.json")
    token_path = os.path.join(grandparent_dir, f"gmail_token_{account_type}.json")

    if not (os.path.exists(oauth_path) and os.path.exists(token_path)):
        print_logger(
            f"oauth_path: {oauth_path} or token_path: {token_path} does not exist"
        )
        deploy_auth_files_from_env(account_type)

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is created
    # automatically when the authorization flow completes for the first time.
    if os.path.exists(token_path):
        print_logger(f"Using:\ntoken file: {token_path}\noauth file: {oauth_path}")
        creds = Credentials.from_authorized_user_file(
            token_path,
            SCOPES,
        )

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                oauth_path,
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(
                token_path,
                "w",
            ) as token:
                token.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)

    return service


# %%
# Sending Email #


def send_message(service, user_id, message):
    try:
        message = (
            service.users().messages().send(userId=user_id, body=message).execute()
        )
        print("Message sent successfully!")
        return message
    except Exception as e:
        print("An error occurred while sending the message:", str(e))


def create_attachment(attachment_path):
    attachment_filename = os.path.basename(attachment_path)
    mime_type, _ = mimetypes.guess_type(attachment_path)
    mime_type, mime_subtype = mime_type.split("/", 1)

    with open(attachment_path, "rb") as file:
        attachment = MIMEBase(mime_type, mime_subtype)
        attachment.set_payload(file.read())

    encoders.encode_base64(attachment)
    attachment.add_header(
        "Content-Disposition", "attachment", filename=attachment_filename
    )
    return attachment


def create_message(
    sender_name,
    sender_email,
    to,
    subject,
    message_text,
    ls_attachment_path=None,
    cc=None,
    bcc=None,
    reply_to=None,
):
    if ls_attachment_path is None:
        ls_attachment_path = []  # Initialize an empty list if not provided
    if cc is None:
        cc = []
    if bcc is None:
        bcc = []

    message = MIMEMultipart()
    message["to"] = ", ".join(to)
    message["from"] = formataddr((sender_name, sender_email))
    message["subject"] = subject

    # Add CC and BCC
    if cc:
        message["cc"] = ", ".join(cc)
    if bcc:
        message["bcc"] = ", ".join(bcc)

    # Set the reply-to header if provided (support list of addresses)
    if reply_to:
        if isinstance(reply_to, list):
            message["Reply-To"] = ", ".join(reply_to)
        else:
            message["Reply-To"] = reply_to

    message.attach(MIMEText(message_text, "html"))  # Set the MIME type to HTML

    if ls_attachment_path:
        for attachment_path in ls_attachment_path:
            attachment = create_attachment(attachment_path)
            message.attach(attachment)

    return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}


def send_email(
    sender_name,
    sender_email,
    to,
    subject,
    message_text,
    account_type="default",
    ls_attachment_path=None,  # Avoid mutable default argument
    cc=None,
    bcc=None,
    reply_to=None,
):
    # Ensure default values for mutable arguments
    if ls_attachment_path is None:
        ls_attachment_path = []
    if cc is None:
        cc = []
    if bcc is None:
        bcc = []

    # Get Gmail service using the account type
    service = get_gmail_service(account_type=account_type)

    # Create the message with attachments, CC, BCC, and Reply-To
    message = create_message(
        sender_name,
        sender_email,
        to,
        subject,
        message_text,
        ls_attachment_path,
        cc,
        bcc,
        reply_to,
    )

    # Send the message
    send_message(service, "me", message)


# %%
# Funtions #


def get_attachment_from_search_string(  # noqa: C901
    search_string,
    output_path,
    output_file_name=None,
    force_download=False,
    account_type="default",
):
    # search gmail for message
    service = get_gmail_service(account_type=account_type)
    results = service.users().messages().list(userId="me", q=search_string).execute()
    all_messages_from_search = results.get("messages", [])
    ls_paths_with_file_names = []
    if not all_messages_from_search:
        print("No messages found.")
        return
    for this_message_from_reults in all_messages_from_search:
        message_id = this_message_from_reults["id"]
        print("message_id: " + str(message_id))

        message_was_already_done = False

        if not os.path.exists(os.path.join(file_dir, "done_message_ids.txt")):
            with open(os.path.join(file_dir, "done_message_ids.txt"), "w") as f:
                f.write("")

        else:
            with open(
                os.path.join(file_dir, "done_message_ids.txt"), "r+"
            ) as message_log:
                for line in message_log:
                    if line.strip() == str(message_id):
                        message_was_already_done = True
                        continue

        if message_was_already_done and not force_download:
            print("Message already downloaded and force_download is False")
            continue
        elif message_was_already_done and force_download:
            print(
                (
                    "Message already downloaded and force_download is True, "
                    "downloading again"
                )
            )

        executed_message = (
            service.users().messages().get(userId="me", id=message_id).execute()
        )

        internal_date_received = executed_message["internalDate"]

        internal_dt_received = pd.to_datetime(
            int(float(internal_date_received) / 1000), unit="s", origin="unix"
        ).strftime(format="%Y-%m-%d")
        str_internal_dt_received = str(internal_dt_received)

        internal_dt_received_with_seconds = pd.to_datetime(
            int(float(internal_date_received) / 1000), unit="s", origin="unix"
        ).strftime(format="%Y.%m.%d %H.%M.%S")
        str_internal_dt_received_with_seconds = str(internal_dt_received_with_seconds)

        message_subject = ""
        for item in executed_message["payload"]["headers"]:
            if item["name"] == "Subject":
                message_subject = item["value"]
                print(f"subject is {message_subject}")
                break
        for part in executed_message["payload"]["parts"]:
            if part["filename"]:
                print("detected attachment type 1")
                original_file_extension = part["filename"].split(".")[-1]
                if output_file_name is None:
                    print("output_file_name is None, using original file name")
                    filename = part["filename"]
                    filename = (
                        filename.replace("/", " ")
                        .replace(":", "")
                        .replace("?", "")
                        .replace("&", "and")
                    )
                elif output_file_name == "original with date":
                    print(
                        (
                            "output_file_name is original with date, "
                            "using original file name with date"
                        )
                    )
                    filename = (
                        part["filename"]
                        + " "
                        + str_internal_dt_received
                        + "."
                        + original_file_extension
                    )
                    filename = (
                        filename.replace("/", " ")
                        .replace(":", "")
                        .replace("?", "")
                        .replace("&", "and")
                    )
                elif output_file_name == "original with date and seconds":
                    print(
                        (
                            "output_file_name is original with date and seconds, "
                            "using original file name with date and seconds"
                        )
                    )
                    filename = (
                        part["filename"]
                        + " "
                        + str_internal_dt_received_with_seconds
                        + "."
                        + original_file_extension
                    )
                    filename = (
                        filename.replace("/", " ")
                        .replace(":", "")
                        .replace("?", "")
                        .replace("&", "and")
                    )
                else:
                    filename = output_file_name
                    filename = (
                        filename.replace("/", " ")
                        .replace(":", "")
                        .replace("?", "")
                        .replace("&", "and")
                    )
                print(f"filename is {filename}")
                attachment = (
                    service.users()
                    .messages()
                    .attachments()
                    .get(
                        id=part["body"]["attachmentId"],
                        userId="me",
                        messageId=message_id,
                    )
                    .execute()
                )
                file_data = base64.urlsafe_b64decode(attachment["data"].encode("utf-8"))
                break
            else:
                try:
                    if part["parts"][0]["filename"]:
                        print("detected attachment type 2")
                        original_file_name = part["parts"][0]["filename"]
                        # replace characters for windows
                        original_file_name = (
                            original_file_name.replace(":", " -")
                            .replace("/", "-")
                            .replace("\\", "-")
                            .replace("&", "-")
                        )
                        original_file_name = (
                            original_file_name.replace("/", " ")
                            .replace(":", "")
                            .replace("?", "")
                            .replace("&", "and")
                        )
                        original_file_extension = original_file_name.split(".")[-1]
                        if output_file_name == "original with subject and datetime":
                            filename = (
                                original_file_name
                                + " "
                                + message_subject
                                + str_internal_dt_received_with_seconds
                                + "."
                                + original_file_extension
                            )
                        elif output_file_name == "domo split":
                            filename = (
                                original_file_name.split(" - ")[0]
                                + " - Active Roster - "
                                + str_internal_dt_received
                                + " - "
                                + original_file_name.replace("|||", "$").split("$")[1]
                                + "."
                                + original_file_extension
                            )
                        elif output_file_name == "highjump":
                            filename = (
                                "highjump file"
                                + " "
                                + str_internal_dt_received_with_seconds
                                + "."
                                + original_file_extension
                            )
                        attachment_id = part["parts"][0]["body"]["attachmentId"]
                        attachment = (
                            service.users()
                            .messages()
                            .attachments()
                            .get(id=attachment_id, userId="me", messageId=message_id)
                            .execute()
                        )
                        file_data = base64.urlsafe_b64decode(
                            attachment["data"].encode("utf-8")
                        )
                        break
                except Exception:
                    print("did not detect attachment type 2")

        path_with_file_name = os.path.join(output_path, filename)
        print(f"path_with_file_name is {path_with_file_name}")
        with open(path_with_file_name, "wb") as f:
            f.write(file_data)
        ls_paths_with_file_names.append(path_with_file_name)

        if not force_download:
            with open(
                os.path.join(file_dir, "done_message_ids.txt"), "a+"
            ) as message_log:
                message_log.write(str(message_id) + "\n")
        else:
            print("force download so not logging message id")

    return ls_paths_with_file_names


# %%
# email addresses #


def get_email_addresses_from_search_string(
    search_string,
    account_type="default",
):
    # search gmail for message
    service = get_gmail_service(account_type=account_type)
    results = service.users().messages().list(userId="me", q=search_string).execute()
    all_messages_from_search = results.get("messages", [])
    print(f"found {len(all_messages_from_search)} messages")

    if not all_messages_from_search:
        print("No messages found.")
        return

    email_addresses = []
    email_regex = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

    for this_message_from_results in all_messages_from_search:
        message_id = this_message_from_results["id"]

        executed_message = (
            service.users().messages().get(userId="me", id=message_id).execute()
        )

        if "parts" in executed_message["payload"]:
            for part in executed_message["payload"]["parts"]:
                print(part["mimeType"])
                print("#" * 30)
                if part["mimeType"] == "text/plain":
                    decoded_data = base64.urlsafe_b64decode(
                        part["body"]["data"].encode("utf-8")
                    ).decode("utf-8")
                    print(decoded_data)
                    email_matches = re.findall(email_regex, decoded_data)
                    email_addresses.extend(email_matches)
                elif part["mimeType"] == "text/html":
                    decoded_data = base64.urlsafe_b64decode(
                        part["body"]["data"].encode("utf-8")
                    ).decode("utf-8")
                    print(decoded_data)
                    email_matches = re.findall(email_regex, decoded_data)
                    email_addresses.extend(email_matches)

    return list(set(email_addresses))


# %%
# Email Bodies #


def get_body_dataframe_from_search_string(
    search_string,
    account_type="default",
):
    # search gmail for message
    service = get_gmail_service(account_type=account_type)
    all_messages_from_search = []
    request = service.users().messages().list(userId="me", q=search_string)

    while request:
        response = request.execute()
        all_messages_from_search.extend(response.get("messages", []))
        request = (
            service.users()
            .messages()
            .list_next(previous_request=request, previous_response=response)
        )

    print(f"found {len(all_messages_from_search)} messages")

    if not all_messages_from_search:
        print("No messages found.")
        return

    # List to store message details
    messages_data = []

    # Iterate through each message
    for message in all_messages_from_search:
        msg = service.users().messages().get(userId="me", id=message["id"]).execute()

        # Extract headers
        headers = msg["payload"]["headers"]
        sender = next(
            header["value"] for header in headers if header["name"].lower() == "from"
        )
        recipient = next(
            header["value"] for header in headers if header["name"].lower() == "to"
        )
        subject = next(
            header["value"] for header in headers if header["name"].lower() == "subject"
        )

        # Extract date from headers
        date_header = next(
            header["value"] for header in headers if header["name"].lower() == "date"
        )
        date = parse(date_header).strftime("%Y-%m-%d %H:%M:%S")

        # Check for attachments
        has_attachment = any(
            part["filename"] for part in msg["payload"].get("parts", [])
        )

        # Extract and decode body
        body = ""
        if "data" in msg["payload"]["body"]:
            body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode(
                "utf-8"
            )
        else:
            parts = msg["payload"].get("parts", [])
            for part in parts:
                if part["partId"] == "0" and "data" in part["body"]:
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                        "utf-8"
                    )
                    break

        # Append data to the list
        messages_data.append(
            {
                "date": date,
                "message_id": message["id"],
                "sender": sender,
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "has_attachment": has_attachment,
            }
        )

    df = pd.DataFrame(messages_data)
    df = df.sort_values(by=["date"], ascending=True)

    return df


# %%
