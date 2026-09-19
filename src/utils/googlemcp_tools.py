# %%
# Imports #

import base64
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import quote

import requests
import yaml

from utils.google_oauth_tools import (
    GOOGLE_TOKEN_URL,
    cached_access_token,
    run_loopback_consent,
)
from utils.inventory_tools import credentials_context, find_credentials_dirs
from utils.secret_tools import resolve_secret

# %%
# Variables #

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
SHEETS_API = "https://sheets.googleapis.com/v4"
DEFAULT_HTTP_TIMEOUT = 30

# Matches the scope the contexts' own mail tooling mints its tokens with -
# gmail.modify covers read, label, trash and send, but never permanent
# deletion.
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"

# Drive is its own grant on the same OAuth client as mail, with the full drive
# scope so files can be saved (a Gmail attachment, say) as well as read.
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"

# <context>_<kind>.yaml -> the label errors use and the types an entry of that
# kind may declare. Both kinds carry the same keys: an OAuth client JSON and a
# google-auth "authorized user" token JSON.
ACCOUNT_KINDS = {
    "googlemail": {"label": "mailbox", "types": ("gmail",)},
    "googledrive": {"label": "drive", "types": ("google_drive",)},
}
REQUIRED_ACCOUNT_KEYS = ("name", "type", "oauth_env", "token_env")

# Gmail caps a single messages.list page at 500.
MAX_GMAIL_RESULTS = 500

# Every Drive file result carries these, so search, metadata and writes all
# describe a file the same way.
DRIVE_FILE_FIELDS = "id,name,mimeType,size,parents,createdTime,modifiedTime,trashed,webViewLink"
DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
MAX_DRIVE_RESULTS = 1000

# Google-native files have no bytes of their own and must be exported, each to
# the plain format a model can read.
DRIVE_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

SHEET_RENDER_OPTIONS = ("FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA")


# %%
# Account config discovery #


def discover_account_configs(kind, credentials_root, repo_root=None):
    """
    Locate every ``kind`` config to load (a key of ``ACCOUNT_KINDS``): an
    optional ``<kind>.yaml`` in the dotfiles repo root (tracked, so
    secrets-free entries only) plus, for each sibling ``*_credentials`` repo,
    an optional ``<context>_<kind>.yaml`` - the same overlay pattern the status
    and calendar boards use. Returns a list of (config_path, base_dir) pairs.
    """
    configs = []
    if repo_root:
        main_config = os.path.join(repo_root, f"{kind}.yaml")
        if os.path.exists(main_config):
            configs.append((main_config, repo_root))
    for credentials_dir in find_credentials_dirs(credentials_root):
        overlay = os.path.join(credentials_dir, f"{credentials_context(credentials_dir)}_{kind}.yaml")
        if os.path.exists(overlay):
            configs.append((overlay, credentials_dir))
    return configs


def load_accounts(kind, credentials_root, repo_root=None, config_path=None):
    """
    Load every discovered ``kind`` config, returning (accounts, config_paths).
    Each account is stamped with ``_base_dir`` (its config's repo root, which
    env_file paths resolve against) and ``_config`` (for error messages).
    Names must be unique across ALL loaded configs of that kind.
    """
    label = ACCOUNT_KINDS[kind]["label"]
    if config_path:
        located = [(config_path, os.path.dirname(os.path.abspath(config_path)))]
    else:
        located = discover_account_configs(kind, credentials_root, repo_root)
    accounts = []
    seen: dict = {}
    for path, base_dir in located:
        for account in _parse_account_config(kind, path):
            if account["name"] in seen:
                raise ValueError(
                    f"Duplicate {kind} {label} name '{account['name']}' in {path} "
                    f"(already defined in {seen[account['name']]})"
                )
            seen[account["name"]] = path
            account["_base_dir"] = base_dir
            account["_config"] = path
            accounts.append(account)
    return accounts, [path for path, _ in located]


def _parse_account_config(kind, config_path):
    """Parse one ``kind`` config and validate its schema, returning a list of account dicts."""
    label, types = ACCOUNT_KINDS[kind]["label"], ACCOUNT_KINDS[kind]["types"]
    with open(config_path, "r", encoding="utf-8") as file_handle:
        payload = yaml.safe_load(file_handle) or []
    if not isinstance(payload, list):
        raise ValueError(f"{config_path}: expected a list of {plural(label)}, got {type(payload).__name__}")
    for account in payload:
        if not isinstance(account, dict):
            raise ValueError(f"{config_path}: expected a list of {label} mappings, got {type(account).__name__}")
        missing = [key for key in REQUIRED_ACCOUNT_KEYS if not account.get(key)]
        if missing:
            raise ValueError(f"{config_path}: {label} {account.get('name', '<unnamed>')} is missing {missing}")
        if account["type"] not in types:
            raise ValueError(
                f"{config_path}: {label} '{account['name']}' has unknown type "
                f"'{account['type']}' (expected one of {types})"
            )
    return payload


def plural(label):
    """Pluralize a config label for error messages - "mailbox" must not become "mailboxs"."""
    return f"{label}es" if label.endswith(("s", "x", "z", "ch", "sh")) else f"{label}s"


def find_by_name(entries, name, label):
    """Pick the one config entry called ``name``, erroring with the valid names when it is not there."""
    for entry in entries:
        if entry["name"] == name:
            return entry
    available = ", ".join(entry["name"] for entry in entries) or "(none configured)"
    raise ValueError(f"unknown {label} '{name}' - configured {plural(label)}: {available}")


# %%
# OAuth credentials #


def _oauth_client(account):
    """(client_id, client_secret) from the account's OAuth client JSON (``installed``/``web`` wrapped or bare)."""
    oauth = json.loads(resolve_secret(account, "oauth_env"))
    installed = oauth.get("installed") or oauth.get("web") or oauth
    return installed.get("client_id"), installed.get("client_secret")


def _account_credentials(account):
    """
    (client_id, client_secret, refresh_token) for a mailbox or drive. The token
    env var holds a google-auth "authorized user" JSON, which normally carries
    the client id/secret itself; when it does not, they come from the OAuth
    client JSON in the oauth env var.
    """
    token = json.loads(resolve_secret(account, "token_env"))
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise ValueError(f"'{account['name']}': {account['token_env']} has no refresh_token")
    client_id, client_secret = token.get("client_id"), token.get("client_secret")
    if not (client_id and client_secret):
        oauth_id, oauth_secret = _oauth_client(account)
        client_id = client_id or oauth_id
        client_secret = client_secret or oauth_secret
    if not (client_id and client_secret):
        raise ValueError(
            f"'{account['name']}': no client_id/client_secret in either "
            f"{account['token_env']} or {account['oauth_env']}"
        )
    return client_id, client_secret, refresh_token


def authorized_user_token(client_id, client_secret, refresh_token, scope):
    """
    The google-auth "authorized user" JSON a ``token_env`` holds, on one line
    because the env file parser reads one line per key.
    """
    return json.dumps(
        {
            "type": "authorized_user",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "token_uri": GOOGLE_TOKEN_URL,
            "scopes": [scope],
        },
        separators=(",", ":"),
    )


def run_drive_auth(drive):
    """
    One-time browser consent for a google_drive entry on its ``oauth_env``
    client, printing the ``token_env`` line to add to its env file. Mail tokens
    are minted by each context's own mail tooling; nothing mints Drive, so the
    server does it through the same loopback consent the calendar board uses.
    """
    client_id, client_secret = _oauth_client(drive)
    if not (client_id and client_secret):
        print(f"'{drive['name']}': no client_id/client_secret in {drive['oauth_env']}")
        return 1
    payload = run_loopback_consent(client_id, client_secret, DRIVE_SCOPE, "google mcp")
    if payload is None:
        return 1
    token = authorized_user_token(client_id, client_secret, payload["refresh_token"], DRIVE_SCOPE)
    env_file = drive.get("env_file", "your env file")
    print(f"\nAuthorization complete. Add this line to {env_file} in {drive.get('_base_dir', '')}:\n")
    print(f"  {drive['token_env']}={token}\n")
    return 0


def gmail_headers(mailbox):
    """Authorization header for a mailbox, off a memoized access token."""
    client_id, client_secret, refresh_token = _account_credentials(mailbox)
    token = cached_access_token(client_id, client_secret, refresh_token, context=mailbox["name"])
    return {"Authorization": f"Bearer {token}"}


def drive_headers(drive):
    """Authorization header for a Drive account (Drive and Sheets APIs), off a memoized access token."""
    client_id, client_secret, refresh_token = _account_credentials(drive)
    token = cached_access_token(client_id, client_secret, refresh_token, context=drive["name"])
    return {"Authorization": f"Bearer {token}"}


def calendar_headers(source):
    """Authorization header for a calendarboard google_calendar source, off a memoized access token."""
    token = cached_access_token(
        resolve_secret(source, "client_id_env"),
        resolve_secret(source, "client_secret_env"),
        resolve_secret(source, "refresh_token_env"),
        context=source["name"],
    )
    return {"Authorization": f"Bearer {token}"}


# %%
# HTTP helpers #


def _raw_request(method, url, headers, **kwargs):
    """One Google API call returning the response itself, raising with the body on anything non-2xx."""
    response = requests.request(method, url, headers=headers, timeout=DEFAULT_HTTP_TIMEOUT, **kwargs)
    if response.status_code // 100 != 2:
        raise ValueError(f"Google API returned {response.status_code} for {method} {url}: {response.text[:300]}")
    return response


def _request(method, url, headers, params=None, payload=None):
    """One Google API JSON call, raising with the response body on anything non-2xx."""
    response = _raw_request(method, url, headers, params=params, json=payload)
    return response.json() if response.content else {}


def _paged(url, headers, params, key, limit=None):
    """Follow nextPageToken, accumulating ``key``, stopping once ``limit`` items are in hand."""
    items: list = []
    params = dict(params or {})
    while True:
        payload = _request("GET", url, headers, params=params)
        items += payload.get(key, [])
        page_token = payload.get("nextPageToken")
        if not page_token or (limit is not None and len(items) >= limit):
            return items[:limit] if limit is not None else items
        params = dict(params, pageToken=page_token)


# %%
# Gmail reads #


def gmail_profile(mailbox):
    """The mailbox's own address and message/thread totals - the cheapest proof the credentials work."""
    return _request("GET", f"{GMAIL_API}/users/me/profile", gmail_headers(mailbox))


def gmail_list_labels(mailbox):
    """Every label, so callers can map names to the ids modify_message needs."""
    payload = _request("GET", f"{GMAIL_API}/users/me/labels", gmail_headers(mailbox))
    return [
        {"id": label.get("id"), "name": label.get("name"), "type": label.get("type")}
        for label in payload.get("labels", [])
    ]


def gmail_search(mailbox, query="", max_results=25, include_spam_trash=False):
    """
    Gmail search (the same query syntax as the web UI's search box), returned
    as a list of summaries: id, threadId, From/To/Subject/Date, snippet and
    labels. Metadata format only - no bodies, so a wide search stays cheap.
    """
    headers = gmail_headers(mailbox)
    max_results = max(1, min(int(max_results), MAX_GMAIL_RESULTS))
    params = {"maxResults": max_results}
    if query:
        params["q"] = query
    if include_spam_trash:
        params["includeSpamTrash"] = "true"
    stubs = _paged(f"{GMAIL_API}/users/me/messages", headers, params, "messages", limit=max_results)
    summaries = []
    for stub in stubs:
        raw = _request(
            "GET",
            f"{GMAIL_API}/users/me/messages/{quote(stub['id'])}",
            headers,
            params={
                "format": "metadata",
                "metadataHeaders": ["From", "To", "Cc", "Subject", "Date"],
            },
        )
        summaries.append(_gmail_summary(raw))
    return summaries


def gmail_list_message_ids(mailbox, query="", include_spam_trash=False):
    """
    Every message id matching ``query`` with its thread id, following every
    page. No per-message fetch, so it stays one call per 500 ids however large
    the result: the way to diff a mailbox against a record of what was already
    processed, then fetch only the new ones with gmail_get_message.
    """
    params = {"maxResults": MAX_GMAIL_RESULTS}
    if query:
        params["q"] = query
    if include_spam_trash:
        params["includeSpamTrash"] = "true"
    stubs = _paged(f"{GMAIL_API}/users/me/messages", gmail_headers(mailbox), params, "messages")
    return [{"id": stub["id"], "thread_id": stub.get("threadId")} for stub in stubs]


def _gmail_summary(raw):
    """Gmail message (metadata format) -> flat summary dict."""
    headers = _header_map(raw.get("payload") or {})
    internal_ms = raw.get("internalDate")
    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        # when Gmail received it, as UTC ISO 8601 - unambiguous where the Date header is free text
        "internal_date": (
            datetime.fromtimestamp(int(internal_ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if internal_ms
            else ""
        ),
        "snippet": raw.get("snippet", ""),
        "labels": raw.get("labelIds", []),
        "unread": "UNREAD" in (raw.get("labelIds") or []),
    }


def _header_map(payload):
    """MIME headers as a lowercased-name -> value dict."""
    return {(header.get("name") or "").lower(): header.get("value") or "" for header in (payload.get("headers") or [])}


def gmail_get_message(mailbox, message_id, body_limit=20000):
    """
    One message in full: the summary fields plus the decoded plain-text body
    (falling back to de-tagged HTML when the sender sent HTML only) and a list
    of attachment names/sizes.
    """
    raw = _request(
        "GET", f"{GMAIL_API}/users/me/messages/{quote(message_id)}", gmail_headers(mailbox), params={"format": "full"}
    )
    payload = raw.get("payload") or {}
    message = _gmail_summary(raw)
    body = _extract_body(payload)
    message["body"] = body[: body_limit - 1] + "…" if len(body) > body_limit else body
    message["attachments"] = _extract_attachments(payload)
    return message


def _walk_parts(payload):
    """Depth-first walk of a MIME tree, yielding every part including the root."""
    yield payload
    for part in payload.get("parts") or []:
        yield from _walk_parts(part)


def _b64url_bytes(data):
    """base64url -> bytes, tolerating the missing padding Gmail sends."""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _decode_part(part):
    """base64url-decode one part's data to text, tolerating bad padding and stray bytes."""
    data = ((part.get("body") or {}).get("data")) or ""
    if not data:
        return ""
    return _b64url_bytes(data).decode("utf-8", errors="replace")


def _extract_body(payload):
    """Prefer every text/plain part joined; fall back to HTML with tags stripped."""
    plain = [_decode_part(part) for part in _walk_parts(payload) if part.get("mimeType") == "text/plain"]
    joined = "\n".join(chunk for chunk in plain if chunk).strip()
    if joined:
        return joined
    html = [_decode_part(part) for part in _walk_parts(payload) if part.get("mimeType") == "text/html"]
    text = re.sub(r"<[^>]+>", " ", "\n".join(chunk for chunk in html if chunk))
    return re.sub(r"[ \t]+", " ", text).strip()


def _extract_attachments(payload):
    """Attachment filename/mime/size/id for every part that has a filename."""
    return [
        {
            "filename": part.get("filename"),
            "mime_type": part.get("mimeType"),
            "size": (part.get("body") or {}).get("size"),
            "attachment_id": (part.get("body") or {}).get("attachmentId"),
        }
        for part in _walk_parts(payload)
        if part.get("filename")
    ]


# %%
# Gmail writes #


def gmail_modify_message(mailbox, message_id, add_labels=None, remove_labels=None):
    """
    Add/remove label ids on one message. ``UNREAD`` and ``STARRED`` are label
    ids too, so this covers mark-read/unread and star/unstar; ids come from
    gmail_list_labels.
    """
    payload = {"addLabelIds": list(add_labels or []), "removeLabelIds": list(remove_labels or [])}
    if not (payload["addLabelIds"] or payload["removeLabelIds"]):
        raise ValueError("gmail_modify_message needs at least one label to add or remove")
    raw = _request(
        "POST",
        f"{GMAIL_API}/users/me/messages/{quote(message_id)}/modify",
        gmail_headers(mailbox),
        payload=payload,
    )
    return {"id": raw.get("id"), "labels": raw.get("labelIds", [])}


def gmail_trash_message(mailbox, message_id, undo=False):
    """
    Move a message to Trash, or back out of it with ``undo``. Recoverable on
    purpose - gmail.modify cannot permanently delete, and this deliberately
    does not try to.
    """
    action = "untrash" if undo else "trash"
    raw = _request("POST", f"{GMAIL_API}/users/me/messages/{quote(message_id)}/{action}", gmail_headers(mailbox))
    return {"id": raw.get("id"), "labels": raw.get("labelIds", []), "action": action}


def gmail_send_message(mailbox, to, subject, body, cc=None, bcc=None, reply_to_message_id=None, thread_id=None):
    """
    Send a plain-text message as the mailbox's own address. Passing
    ``reply_to_message_id`` threads the reply properly (In-Reply-To/References
    off that message's Message-ID) and defaults thread_id to its thread.
    """
    message = EmailMessage()
    message["To"] = _join_addresses(to)
    if cc:
        message["Cc"] = _join_addresses(cc)
    if bcc:
        message["Bcc"] = _join_addresses(bcc)
    message["Subject"] = subject
    message.set_content(body)
    payload = {}
    if reply_to_message_id:
        original = _request(
            "GET",
            f"{GMAIL_API}/users/me/messages/{quote(reply_to_message_id)}",
            gmail_headers(mailbox),
            params={"format": "metadata", "metadataHeaders": ["Message-ID", "References"]},
        )
        headers = _header_map(original.get("payload") or {})
        original_id = headers.get("message-id", "")
        if original_id:
            message["In-Reply-To"] = original_id
            message["References"] = f"{headers.get('references', '')} {original_id}".strip()
        payload["threadId"] = thread_id or original.get("threadId")
    elif thread_id:
        payload["threadId"] = thread_id
    payload["raw"] = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    raw = _request("POST", f"{GMAIL_API}/users/me/messages/send", gmail_headers(mailbox), payload=payload)
    return {"id": raw.get("id"), "thread_id": raw.get("threadId"), "labels": raw.get("labelIds", [])}


def _join_addresses(value):
    """Accept a single address or a list of them; Gmail wants one comma-joined header."""
    if isinstance(value, str):
        return value
    return ", ".join(value)


def _gmail_attachment(mailbox, message_id, filename):
    """(bytes, mime_type) of the one attachment called ``filename`` on a message."""
    headers = gmail_headers(mailbox)
    raw = _request("GET", f"{GMAIL_API}/users/me/messages/{quote(message_id)}", headers, params={"format": "full"})
    payload = raw.get("payload") or {}
    parts = [part for part in _walk_parts(payload) if part.get("filename") == filename]
    if not parts:
        available = ", ".join(item["filename"] for item in _extract_attachments(payload)) or "(none)"
        raise ValueError(f"message {message_id} has no attachment '{filename}' - attachments: {available}")
    if len(parts) > 1:
        raise ValueError(f"message {message_id} has {len(parts)} attachments named '{filename}'")
    body = parts[0].get("body") or {}
    data = body.get("data")
    if not data:
        data = _request(
            "GET",
            f"{GMAIL_API}/users/me/messages/{quote(message_id)}/attachments/{quote(body['attachmentId'])}",
            headers,
        ).get("data", "")
    return _b64url_bytes(data), parts[0].get("mimeType") or "application/octet-stream"


def gmail_save_attachment_to_drive(mailbox, drive, message_id, filename, parent_id="root", name=""):
    """
    Upload one Gmail attachment straight into a Drive folder, stored as-is.
    Nothing touches local disk; ``name`` defaults to the attachment's filename.
    """
    data, mime_type = _gmail_attachment(mailbox, message_id, filename)
    metadata = {"name": name or filename, "parents": [parent_id]}
    return _upload(drive, "POST", f"{DRIVE_UPLOAD_API}/files", metadata, data, mime_type)


# %%
# Drive reads #


def drive_about(drive):
    """The account the Drive token belongs to and its storage quota - the cheapest proof the credentials work."""
    raw = _request(
        "GET",
        f"{DRIVE_API}/about",
        drive_headers(drive),
        params={"fields": "user(displayName,emailAddress),storageQuota"},
    )
    return {"user": raw.get("user", {}), "storage_quota": raw.get("storageQuota", {})}


def drive_search(drive, query="", max_results=50, order_by="modifiedTime desc"):
    """
    Files matching Drive's own query syntax (``name contains 'x'``,
    ``'<folder id>' in parents``, ``mimeType = '...'``) across My Drive and
    every shared drive. Trashed files are left out unless the query itself
    says something about ``trashed``.
    """
    max_results = max(1, min(int(max_results), MAX_DRIVE_RESULTS))
    if "trashed" not in query:
        query = f"({query}) and trashed = false" if query else "trashed = false"
    params = {
        "q": query,
        "fields": f"nextPageToken,files({DRIVE_FILE_FIELDS})",
        "pageSize": max_results,
        "orderBy": order_by,
        "corpora": "allDrives",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    return _paged(f"{DRIVE_API}/files", drive_headers(drive), params, "files", limit=max_results)


def drive_get_metadata(drive, file_id):
    """One file's name, type, size, folders, times and link."""
    return _request(
        "GET",
        f"{DRIVE_API}/files/{quote(file_id)}",
        drive_headers(drive),
        params={"fields": DRIVE_FILE_FIELDS, "supportsAllDrives": "true"},
    )


def _drive_file_bytes(drive, file_id):
    """(metadata, bytes) of a file: Google-native files exported per DRIVE_EXPORT_MIME, the rest as stored."""
    metadata = drive_get_metadata(drive, file_id)
    mime_type = metadata.get("mimeType", "")
    if mime_type in DRIVE_EXPORT_MIME:
        url, params = f"{DRIVE_API}/files/{quote(file_id)}/export", {"mimeType": DRIVE_EXPORT_MIME[mime_type]}
    elif mime_type.startswith("application/vnd.google-apps."):
        raise ValueError(f"'{metadata.get('name')}' is a {mime_type}, which has no export format here")
    else:
        url, params = f"{DRIVE_API}/files/{quote(file_id)}", {"alt": "media", "supportsAllDrives": "true"}
    return metadata, _raw_request("GET", url, drive_headers(drive), params=params).content


def drive_read_file(drive, file_id, max_chars=100000):
    """
    A file's text: Docs and Slides exported as plain text, Sheets as CSV (first
    tab only - sheets_get_values reaches the rest), stored files decoded as
    UTF-8. Binary files are refused rather than returned as mojibake.
    """
    metadata, content = _drive_file_bytes(drive, file_id)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            f"'{metadata.get('name')}' ({metadata.get('mimeType')}) is binary - use drive_download_file"
        ) from None
    return {
        "id": metadata.get("id"),
        "name": metadata.get("name"),
        "mime_type": metadata.get("mimeType"),
        "text": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def drive_download_file(drive, file_id, local_path):
    """Save a file's bytes (Google-native files exported as for drive_read_file) to a path that does not exist yet."""
    path = os.path.abspath(os.path.expanduser(local_path))
    if os.path.exists(path):
        raise ValueError(f"{path} already exists - pick a new path, downloads never overwrite")
    metadata, content = _drive_file_bytes(drive, file_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as file_handle:
        file_handle.write(content)
    return {"id": metadata.get("id"), "name": metadata.get("name"), "path": path, "bytes": len(content)}


def sheets_get_values(drive, spreadsheet_id, cell_range, render="FORMATTED_VALUE"):
    """
    One A1 range of a spreadsheet (``'Tab name'!A1:Z50``, or a bare tab name for
    the whole tab) as rows. ``render`` FORMULA returns each cell's formula
    instead of its value, which is how to see what a sheet pulls from.
    """
    if render not in SHEET_RENDER_OPTIONS:
        raise ValueError(f"render must be one of {SHEET_RENDER_OPTIONS}, got '{render}'")
    raw = _request(
        "GET",
        f"{SHEETS_API}/spreadsheets/{quote(spreadsheet_id)}/values/{quote(cell_range)}",
        drive_headers(drive),
        params={"valueRenderOption": render},
    )
    return {"range": raw.get("range"), "values": raw.get("values", [])}


# %%
# Drive writes #


def _content_bytes(content, local_path):
    """The bytes to upload: exactly one of text ``content`` or a ``local_path`` file."""
    if bool(content) == bool(local_path):
        raise ValueError("pass exactly one of content (text) or local_path (a file on this machine)")
    if local_path:
        with open(os.path.expanduser(local_path), "rb") as file_handle:
            return file_handle.read()
    return content.encode("utf-8")


def _upload(drive, method, url, metadata, data, mime_type):
    """
    Resumable upload: one call opens the session with the metadata, a second
    sends the bytes. Any size, and the same path for a create (POST) and an
    in-place content replacement (PATCH). The bytes are stored exactly as sent -
    Drive only converts when the metadata asks for a Google-native type.
    """
    headers = drive_headers(drive)
    session = _raw_request(
        method,
        url,
        {**headers, "X-Upload-Content-Type": mime_type},
        params={"uploadType": "resumable", "supportsAllDrives": "true", "fields": DRIVE_FILE_FIELDS},
        json=metadata,
    )
    location = session.headers.get("Location")
    if not location:
        raise ValueError(f"Drive opened no upload session for {method} {url}")
    return _raw_request("PUT", location, {**headers, "Content-Type": mime_type}, data=data).json()


def drive_upload_file(drive, name, parent_id="root", content="", local_path="", mime_type=""):
    """
    Create a file in ``parent_id`` from text ``content`` or a ``local_path``
    file. Drive allows duplicate names in one folder, so this always creates a
    new file - drive_update_file replaces an existing one.
    """
    data = _content_bytes(content, local_path)
    mime_type = (
        mime_type
        or mimetypes.guess_type(local_path or name)[0]
        or ("text/plain" if content else "application/octet-stream")
    )
    return _upload(drive, "POST", f"{DRIVE_UPLOAD_API}/files", {"name": name, "parents": [parent_id]}, data, mime_type)


def drive_update_file(drive, file_id, content="", local_path="", mime_type=""):
    """Replace a file's content in place, keeping its id, name, folder and sharing."""
    data = _content_bytes(content, local_path)
    mime_type = mime_type or drive_get_metadata(drive, file_id).get("mimeType") or "application/octet-stream"
    return _upload(drive, "PATCH", f"{DRIVE_UPLOAD_API}/files/{quote(file_id)}", {}, data, mime_type)


def drive_create_folder(drive, name, parent_id="root"):
    """Create a folder in ``parent_id``."""
    return _request(
        "POST",
        f"{DRIVE_API}/files",
        drive_headers(drive),
        params={"supportsAllDrives": "true", "fields": DRIVE_FILE_FIELDS},
        payload={"name": name, "mimeType": DRIVE_FOLDER_MIME, "parents": [parent_id]},
    )


def drive_trash_file(drive, file_id, undo=False):
    """
    Move a file or folder to Drive's trash, or restore it with ``undo``.
    Recoverable for 30 days; nothing here deletes a file permanently.
    """
    return _request(
        "PATCH",
        f"{DRIVE_API}/files/{quote(file_id)}",
        drive_headers(drive),
        params={"supportsAllDrives": "true", "fields": DRIVE_FILE_FIELDS},
        payload={"trashed": not undo},
    )


# %%
# Calendar reads #


def calendar_list_calendars(source):
    """Every calendar on the account, as the web UI's sidebar shows them."""
    calendars = _paged(
        f"{CALENDAR_API}/users/me/calendarList", calendar_headers(source), {"minAccessRole": "reader"}, "items"
    )
    return [
        {
            "id": calendar.get("id"),
            "name": calendar.get("summaryOverride") or calendar.get("summary") or calendar.get("id"),
            "primary": bool(calendar.get("primary")),
            "access_role": calendar.get("accessRole"),
        }
        for calendar in calendars
    ]


def calendar_get_event(source, event_id, calendar_id="primary"):
    """
    One event with the provenance fields the board's summary drops: ``creator``
    (who made the event) and ``organizer`` (whose calendar owns it), plus the
    full attendee list with per-person response status.

    Google records no per-attendee provenance, so who added any individual
    guest after the fact is not answerable from this - creator/organizer is as
    close as the API gets.
    """
    raw = _request(
        "GET",
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events/{quote(event_id)}",
        calendar_headers(source),
    )
    return _event_detail(raw)


def _event_detail(raw):
    """Calendar API event -> detail dict (creator/organizer/attendees kept verbatim)."""
    return {
        "id": raw.get("id"),
        "status": raw.get("status"),
        "title": raw.get("summary") or "(no title)",
        "start": raw.get("start"),
        "end": raw.get("end"),
        "location": raw.get("location") or "",
        "description": raw.get("description") or "",
        "creator": raw.get("creator") or {},
        "organizer": raw.get("organizer") or {},
        "attendees": [
            {
                "email": attendee.get("email"),
                "name": attendee.get("displayName") or "",
                "response": attendee.get("responseStatus"),
                "optional": bool(attendee.get("optional")),
                "organizer": bool(attendee.get("organizer")),
                "self": bool(attendee.get("self")),
            }
            for attendee in raw.get("attendees") or []
        ],
        "recurring_event_id": raw.get("recurringEventId") or "",
        "created": raw.get("created") or "",
        "updated": raw.get("updated") or "",
        "link": raw.get("hangoutLink") or raw.get("htmlLink") or "",
    }


def calendar_search_events(source, query="", calendar_id="primary", time_min=None, time_max=None, max_results=25):
    """
    Events on one calendar, optionally full-text filtered by ``query``, as
    detail dicts. Recurring events arrive pre-expanded (singleEvents), so
    ``time_min``/``time_max`` (RFC3339 strings) bound real occurrences.
    """
    params = {"singleEvents": "true", "orderBy": "startTime", "maxResults": max(1, min(int(max_results), 250))}
    if query:
        params["q"] = query
    if time_min:
        params["timeMin"] = time_min
    if time_max:
        params["timeMax"] = time_max
    raws = _paged(
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events",
        calendar_headers(source),
        params,
        "items",
        limit=params["maxResults"],
    )
    return [_event_detail(raw) for raw in raws]


# %%
# Calendar writes #


def calendar_create_event(source, summary, start, end, calendar_id="primary", **fields):
    """
    Create an event. ``start``/``end`` are Calendar API date/dateTime objects
    (e.g. ``{"dateTime": "2026-08-27T10:00:00-05:00"}`` or
    ``{"date": "2026-08-27"}``). Extra ``fields`` (description, location,
    attendees, recurrence, ...) pass straight through.
    """
    payload = dict(fields, summary=summary, start=start, end=end)
    send_updates = payload.pop("send_updates", "none")
    raw = _request(
        "POST",
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events",
        calendar_headers(source),
        params={"sendUpdates": send_updates},
        payload=payload,
    )
    return _event_detail(raw)


def calendar_update_event(source, event_id, calendar_id="primary", send_updates="none", **fields):
    """
    Patch an existing event - only the passed ``fields`` change. Same field
    names as calendar_create_event.
    """
    if not fields:
        raise ValueError("calendar_update_event needs at least one field to change")
    raw = _request(
        "PATCH",
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events/{quote(event_id)}",
        calendar_headers(source),
        params={"sendUpdates": send_updates},
        payload=fields,
    )
    return _event_detail(raw)


def calendar_delete_event(source, event_id, calendar_id="primary", send_updates="none"):
    """Delete an event. Unlike Gmail's trash this is not recoverable through the API."""
    _request(
        "DELETE",
        f"{CALENDAR_API}/calendars/{quote(calendar_id)}/events/{quote(event_id)}",
        calendar_headers(source),
        params={"sendUpdates": send_updates},
    )
    return {"id": event_id, "calendar_id": calendar_id, "deleted": True}


# %%
