#!/bin/bash
# S3/BI credentials (Linux). Wrapper around aws_credential_extractor.sh.
# Usage: source aws_credential_extractor_s3.sh
source "$(dirname "${BASH_SOURCE[0]}")/aws_credential_extractor.sh" --profile BIDevSSO --role BIDeveloper --region eu-west-1
