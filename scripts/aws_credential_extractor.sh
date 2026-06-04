#!/bin/bash
# Unified AWS SSO credential extractor.
# Fetches temporary credentials and exports them into the current shell.
#
# Usage: source aws_credential_extractor.sh [--profile PROFILE] [--role ROLE] [--region REGION]
#
# Defaults: profile=BIDevSSO, role=BIDeveloper, region=eu-west-1

_aws_profile="${AWS_PROFILE_OVERRIDE:-BIDevSSO}"
_aws_role="BIDeveloper"
_aws_region="eu-west-1"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile) _aws_profile="$2"; shift 2 ;;
        --role)    _aws_role="$2";    shift 2 ;;
        --region)  _aws_region="$2";  shift 2 ;;
        *) echo "Unknown argument: $1" >&2; return 1 2>/dev/null || exit 1 ;;
    esac
done

# Find the latest SSO cache file (OS-portable)
if [[ "$(uname)" == "Darwin" ]]; then
    LATEST_SSO_FILE=$(find ~/.aws/sso/cache -type f -name "*.json" -exec stat -f "%m %N" {} + | sort -n | tail -1 | cut -d ' ' -f 2-)
else
    LATEST_SSO_FILE=$(find ~/.aws/sso/cache -type f -name "*.json" -printf '%T@ %p\n' | sort -n | tail -1 | cut -d ' ' -f 2-)
fi

AWS_ACCESS_TOKEN=$(jq -r '.accessToken' "$LATEST_SSO_FILE")
export AWS_ACCESS_TOKEN

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --output text --query 'Account' --profile "$_aws_profile")
export AWS_ACCOUNT_ID

_creds_file=~/aws_temporary_credentials.json
aws sso get-role-credentials \
    --role-name "$_aws_role" \
    --account-id "$AWS_ACCOUNT_ID" \
    --access-token "$AWS_ACCESS_TOKEN" \
    --output json \
    --region "$_aws_region" > "$_creds_file"

AWS_ACCESS_KEY_ID=$(jq -r '.roleCredentials.accessKeyId' "$_creds_file")
export AWS_ACCESS_KEY_ID

AWS_SECRET_ACCESS_KEY=$(jq -r '.roleCredentials.secretAccessKey' "$_creds_file")
export AWS_SECRET_ACCESS_KEY

AWS_SESSION_TOKEN=$(jq -r '.roleCredentials.sessionToken' "$_creds_file")
export AWS_SESSION_TOKEN

echo "AWS credentials exported: profile=$_aws_profile role=$_aws_role region=$_aws_region"
unset _aws_profile _aws_role _aws_region _creds_file
