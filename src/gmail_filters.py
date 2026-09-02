# %%
# Imports #

"""
Gmail filters as code, per context.

Desired state lives in ``<context>_credentials/<context>_gmail_filters.yaml``
(private repos, never on GitHub - the filters name real senders). This script
makes Gmail match that file: it creates labels and filters the file has, and
deletes filters the file does not have. It never edits a filter (Gmail cannot;
an edit is delete + create), never deletes a label, never trashes or deletes a
message, and refuses any action that would send mail to SPAM or TRASH.

The yaml names the mailbox (from ``<context>_googlemail.yaml``) and the
account address; the script checks Gmail's profile against that address before
anything else, so one context's rules cannot land in another context's inbox.

    uv run python src/gmail_filters.py --context personal plan
    uv run python src/gmail_filters.py --context personal apply
    uv run python src/gmail_filters.py --context personal backfill [--only NAME ...] [--execute]
"""

import argparse
import json
import os
import sys

import yaml
from config import grandparent_dir, parent_dir
from utils import googlemcp_tools as gtools
from utils.inventory_tools import credentials_context, find_credentials_dirs

# %%
# Variables #

REPO_ROOT = parent_dir
CREDENTIALS_ROOT = grandparent_dir
GMAIL_API = gtools.GMAIL_API + "/users/me"
PAGE_SIZE = gtools.MAX_GMAIL_RESULTS
BATCH_MODIFY_LIMIT = 1000
SYSTEM_LABELS = {"STARRED", "IMPORTANT", "INBOX", "SPAM", "UNREAD", "TRASH"}
# Labels a filter may never ADD: mail must never be routed into either.
FORBIDDEN_ADDS = {"SPAM", "TRASH"}
# Gmail allows ONE user label per filter ("Too many user labels in filter"), so
# a yaml entry adding several is expanded into one Gmail filter per user label
# with identical criteria - the first carries the system labels and removals.


# %%
# Config #


def context_config(context, kind):
    """``<context>_credentials/<context>_<kind>.yaml`` or None when that repo/config is absent."""
    for credentials_dir in find_credentials_dirs(CREDENTIALS_ROOT):
        if credentials_context(credentials_dir) == context:
            path = os.path.join(credentials_dir, f"{context}_{kind}.yaml")
            return path if os.path.exists(path) else None
    return None


def load_config(path):
    with open(path, "r", encoding="utf-8") as file_handle:
        config = yaml.safe_load(file_handle) or {}
    for key in ("mailbox", "account", "filters"):
        if not config.get(key):
            sys.exit(f"{path}: missing top-level '{key}'")
    names = [f.get("name") for f in config["filters"]]
    if not all(names) or len(set(names)) != len(names):
        sys.exit(f"{path}: every filter needs a unique 'name'")
    for f in config["filters"]:
        forbidden = FORBIDDEN_ADDS & set(f.get("action", {}).get("add", []))
        if forbidden:
            sys.exit(f"{path}: filter '{f['name']}' would add {sorted(forbidden)} - refusing")
        if not f.get("criteria"):
            sys.exit(f"{path}: filter '{f['name']}' has no criteria")
    return config


# %%
# Gmail #


class Gmail:
    def __init__(self, context, mailbox_name, account):
        googlemail = context_config(context, "googlemail")
        if not googlemail:
            sys.exit(f"no {context}_googlemail.yaml found under {CREDENTIALS_ROOT}")
        mailboxes, _ = gtools.load_mailboxes(CREDENTIALS_ROOT, REPO_ROOT, config_path=googlemail)
        self.mailbox = gtools.find_by_name(mailboxes, mailbox_name, "mailbox")
        profile = self.get("profile")
        if profile.get("emailAddress", "").lower() != account.lower():
            sys.exit(
                f"mailbox '{mailbox_name}' is {profile.get('emailAddress')} but the yaml says {account} - refusing"
            )
        self.account = account

    def _headers(self):
        return {**gtools.gmail_headers(self.mailbox), "Content-Type": "application/json"}

    def get(self, path, params=None):
        return gtools._request("GET", f"{GMAIL_API}/{path}", self._headers(), params=params)

    def post(self, path, payload):
        return gtools._request("POST", f"{GMAIL_API}/{path}", self._headers(), payload=payload)

    def delete_filter(self, filter_id):
        gtools._request("DELETE", f"{GMAIL_API}/settings/filters/{filter_id}", self._headers())

    def labels(self):
        return self.get("labels").get("labels", [])

    def filters(self):
        return self.get("settings/filters").get("filter", [])

    def message_ids(self, query):
        ids, page_token = [], None
        while True:
            params = {"q": query, "maxResults": PAGE_SIZE}
            if page_token:
                params["pageToken"] = page_token
            page = self.get("messages", params=params)
            ids.extend(m["id"] for m in page.get("messages", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                return ids

    def batch_modify(self, ids, action):
        """Relabel only - the payload can carry nothing but label ids, so no trash/delete path exists."""
        for start in range(0, len(ids), BATCH_MODIFY_LIMIT):
            self.post("messages/batchModify", {"ids": ids[start:start + BATCH_MODIFY_LIMIT], **action})


# %%
# Desired vs live #


def label_names_used(filters):
    names = set()
    for f in filters:
        names.update(f.get("action", {}).get("add", []))
        names.update(f.get("action", {}).get("remove", []))
    return names - SYSTEM_LABELS


def resolve_action(action, label_ids):
    body = {}
    for key, api_key in (("add", "addLabelIds"), ("remove", "removeLabelIds")):
        if action.get(key):
            body[api_key] = sorted(label_ids[name] if name in label_ids else name for name in action[key])
    return body


def normalize(criteria, action):
    """Comparison key: criteria verbatim, label id lists sorted."""
    action = {k: sorted(v) if isinstance(v, list) else v for k, v in action.items()}
    return json.dumps({"criteria": criteria, "action": action}, sort_keys=True)


def expand(entry):
    """One (name, criteria, action) per Gmail filter the entry needs - see the one-user-label note."""
    action = entry.get("action", {})
    user_labels = [name for name in action.get("add", []) if name not in SYSTEM_LABELS]
    if len(user_labels) <= 1:
        return [(entry["name"], entry["criteria"], action)]
    first = {"add": [n for n in action["add"] if n not in user_labels[1:]], "remove": action.get("remove", [])}
    expanded = [(entry["name"], entry["criteria"], first)]
    for label in user_labels[1:]:
        expanded.append((f"{entry['name']} [+{label}]", entry["criteria"], {"add": [label]}))
    return expanded


def compute_plan(filters, live, label_ids):
    desired = {}
    for entry in filters:
        for name, criteria, action in expand(entry):
            body = {"criteria": dict(criteria), "action": resolve_action(action, label_ids)}
            desired[normalize(body["criteria"], body["action"])] = ({**entry, "name": name}, body)
    live_keys = {normalize(lf.get("criteria", {}), lf.get("action", {})): lf for lf in live}
    create = [desired[key] for key in desired if key not in live_keys]
    unchanged = [desired[key][0]["name"] for key in desired if key in live_keys]
    prune = [lf for key, lf in live_keys.items() if key not in desired]
    return create, unchanged, prune


def describe(criteria, action, label_names):
    names = {k: [label_names.get(i, i) for i in v] for k, v in action.items() if isinstance(v, list)}
    return f"{json.dumps(criteria)} -> {json.dumps(names)}"


def criteria_query(criteria):
    """Gmail search equivalent of a filter's criteria, for backfilling existing mail."""
    parts = []
    for key, prefix in (("from", "from:"), ("to", "to:"), ("subject", "subject:")):
        if criteria.get(key):
            parts.append(f"{prefix}({criteria[key]})")
    if criteria.get("query"):
        parts.append(f"({criteria['query']})")
    if criteria.get("negatedQuery"):
        parts.append(f"-({criteria['negatedQuery']})")
    if criteria.get("hasAttachment"):
        parts.append("has:attachment")
    return " ".join(parts)


# %%
# Commands #


def ensure_labels(gmail, filters, label_ids, label_names, apply):
    for name in sorted(label_names_used(filters) - set(label_ids)):
        if apply:
            created = gmail.post("labels", {"name": name})
            label_ids[name], label_names[created["id"]] = created["id"], name
            print(f"label   created   {name} ({created['id']})")
        else:
            print(f"label   create    {name}")


def backfill_one(gmail, entry, action, execute):
    query = criteria_query(entry["criteria"])
    ids = gmail.message_ids(query)
    print(f"{entry['name']:28} {len(ids):6} messages  q={query}")
    if execute and ids:
        gmail.batch_modify(ids, action)
        print(f"{'':28} relabelled")
    return len(ids)


def cmd_plan(gmail, filters, apply=False):
    labels = gmail.labels()
    label_ids = {lb["name"]: lb["id"] for lb in labels}
    label_names = {lb["id"]: lb["name"] for lb in labels}
    ensure_labels(gmail, filters, label_ids, label_names, apply)
    create, unchanged, prune = compute_plan(filters, gmail.filters(), label_ids)
    for name in unchanged:
        print(f"filter  unchanged {name}")
    for entry, body in create:
        if apply:
            created = gmail.post("settings/filters", body)
            print(f"filter  created   {entry['name']} ({created['id']})")
        else:
            print(f"filter  create    {entry['name']}: {describe(body['criteria'], body['action'], label_names)}")
    for lf in prune:
        if apply:
            gmail.delete_filter(lf["id"])
            print(f"filter  deleted   {lf['id']}")
        else:
            live = describe(lf.get("criteria", {}), lf.get("action", {}), label_names)
            print(f"filter  delete    {lf['id']}: {live}")
    print(f"\n{len(create)} to create, {len(unchanged)} unchanged, {len(prune)} to delete")
    if apply:
        created_names = {entry["name"].split(" [+")[0] for entry, _ in create}
        for entry in filters:
            if entry.get("backfill") and entry["name"] in created_names:
                backfill_one(gmail, entry, resolve_action(entry.get("action", {}), label_ids), execute=True)


def cmd_backfill(gmail, filters, only=None, execute=False):
    label_ids = {lb["name"]: lb["id"] for lb in gmail.labels()}
    total = 0
    for entry in filters:
        if only and entry["name"] not in only:
            continue
        missing = label_names_used([entry]) - set(label_ids)
        if missing:
            print(f"{entry['name']}: skipped, labels not in Gmail yet: {sorted(missing)} (run apply first)")
            continue
        total += backfill_one(gmail, entry, resolve_action(entry.get("action", {}), label_ids), execute)
    print(f"\n{total} messages {'relabelled' if execute else 'would be relabelled (dry run; add --execute)'}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--context", required=True, help="credentials context whose <context>_gmail_filters.yaml to use"
    )
    parser.add_argument("--config", help="explicit yaml path instead of discovering it from --context")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="show what apply would do; no writes")
    sub.add_parser(
        "apply", help="create missing labels/filters, delete filters not in the yaml, backfill flagged ones"
    )
    backfill = sub.add_parser("backfill", help="apply each filter's labels to existing matching mail")
    backfill.add_argument("--only", nargs="*", help="filter names to limit to")
    backfill.add_argument("--execute", action="store_true", help="really relabel; default is count only")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config_path = args.config or context_config(args.context, "gmail_filters")
    if not config_path:
        sys.exit(f"no {args.context}_gmail_filters.yaml found under {CREDENTIALS_ROOT}")
    config = load_config(config_path)
    gmail = Gmail(args.context, config["mailbox"], config["account"])
    print(f"{config_path} -> {gmail.account}\n")
    if args.command == "plan":
        cmd_plan(gmail, config["filters"])
    elif args.command == "apply":
        cmd_plan(gmail, config["filters"], apply=True)
    else:
        cmd_backfill(gmail, config["filters"], only=args.only, execute=args.execute)


# %%
# Main #

if __name__ == "__main__":
    main()
