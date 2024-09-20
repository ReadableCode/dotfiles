#!/bin/bash

# Find file created by the configure command
LATEST_SSO_FILE=$(find ~/.aws/sso/cache -type f -name "*.json" -printf '%T@ %p\n' | sort -n | tail -1 | cut -d ' ' -f 2-)

# Read and export the access token
AWS_ACCESS_TOKEN=$(jq -r '.accessToken' "$LATEST_SSO_FILE")
export AWS_ACCESS_TOKEN

# Get account ID and export
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --output text --query 'Account' --profile sso-eks-dwh-basic)
export AWS_ACCOUNT_ID

# Get temporary credentials and save to a file
aws sso get-role-credentials --role-name sso_eks_basic --account-id "$AWS_ACCOUNT_ID" --access-token "$AWS_ACCESS_TOKEN" --output json --region eu-west-1 > ~/aws_temporary_credentials.json

# Extract credentials from the JSON file and export each
AWS_ACCESS_KEY_ID=$(jq -r '.roleCredentials.accessKeyId' ~/aws_temporary_credentials.json)
export AWS_ACCESS_KEY_ID

AWS_SECRET_ACCESS_KEY=$(jq -r '.roleCredentials.secretAccessKey' ~/aws_temporary_credentials.json)
export AWS_SECRET_ACCESS_KEY

AWS_SESSION_TOKEN=$(jq -r '.roleCredentials.sessionToken' ~/aws_temporary_credentials.json)
export AWS_SESSION_TOKEN
