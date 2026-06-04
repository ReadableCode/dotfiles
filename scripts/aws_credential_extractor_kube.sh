#!/bin/bash
# Kube/EKS credentials. Wrapper around aws_credential_extractor.sh.
# Usage: source aws_credential_extractor_kube.sh
source "$(dirname "${BASH_SOURCE[0]}")/aws_credential_extractor.sh" --profile sso-eks-dwh-basic --role sso_eks_basic --region eu-west-1
