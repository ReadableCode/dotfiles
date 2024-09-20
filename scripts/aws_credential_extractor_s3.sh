#!/bin/bash

# Find file created by the configure command
LATEST_SSO_FILE=$(find ~/.aws/sso/cache -type f -name "*.json" -printf '%T@ %p\n' | sort -n | tail -1 | cut -d ' ' -f 2-)

# Read and export the access token
AWS_ACCESS_TOKEN=$(jq -r '.accessToken' "$LATEST_SSO_FILE")
export AWS_ACCESS_TOKEN

# Get account ID and export
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --output text --query 'Account' --profile BIDevSSO)
export AWS_ACCOUNT_ID

# Get temporary credentials and save to a file
aws sso get-role-credentials --role-name BIDeveloper --account-id "$AWS_ACCOUNT_ID" --access-token "$AWS_ACCESS_TOKEN" --output json --region eu-west-1 >~/aws_temporary_credentials.json
