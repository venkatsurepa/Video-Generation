#!/usr/bin/env bash
# ============================================================
# Deploy Remotion Lambda to AWS
# ============================================================
# This script deploys the CrimeMill video renderer to AWS Lambda.
#
# Prerequisites:
#   - AWS CLI configured with credentials (aws configure)
#   - Node.js 18+ installed
#   - IAM user/role with permissions from remotion-lambda-policy.json
#
# What it does:
#   1. Installs Node.js dependencies
#   2. Deploys Lambda function (2048 MB RAM, 5-min timeout)
#   3. Deploys Remotion site bundle to S3
#
# Cost: ~$0.10-0.11 per 10-minute video render
#        Lambda duration: 56-61 seconds typical
#        S3 storage: negligible (cleaned up after download)
# ============================================================

set -euo pipefail

REGION="${REMOTION_AWS_REGION:-us-east-1}"
SITE_NAME="crimemill-video"
MEMORY=2048
DISK=2048
TIMEOUT=300

cd "$(dirname "$0")/.."

echo "=== CrimeMill Remotion Lambda Deployment ==="
echo "Region: ${REGION}"
echo ""

# -------------------------------------------------------
# 1. Install dependencies
# -------------------------------------------------------
echo "--- Installing dependencies ---"
npm ci
echo ""

# -------------------------------------------------------
# 2. Deploy Lambda function
# -------------------------------------------------------
echo "--- Deploying Lambda function ---"
echo "  Memory: ${MEMORY} MB"
echo "  Disk:   ${DISK} MB"
echo "  Timeout: ${TIMEOUT}s"
echo ""

npx remotion lambda functions deploy \
  --memory "${MEMORY}" \
  --disk "${DISK}" \
  --timeout "${TIMEOUT}" \
  --region "${REGION}" \
  --yes

echo ""

# -------------------------------------------------------
# 3. Deploy Remotion site (bundle to S3)
# -------------------------------------------------------
echo "--- Deploying Remotion site ---"

npx remotion lambda sites create \
  src/index.ts \
  --site-name "${SITE_NAME}" \
  --region "${REGION}" \
  --yes

echo ""

# -------------------------------------------------------
# 4. Output instructions
# -------------------------------------------------------
echo "=== Deployment Complete ==="
echo ""
echo "Note the function name and serve URL from the output above."
echo "Set these in your backend environment (.env or Railway variables):"
echo ""
echo "  REMOTION_LAMBDA_FUNCTION_NAME=<function-name-from-output>"
echo "  REMOTION_SERVE_URL=<serve-url-from-output>"
echo "  REMOTION_AWS_REGION=${REGION}"
echo ""
echo "To verify the deployment:"
echo "  npx remotion lambda functions ls --region ${REGION}"
echo "  npx remotion lambda sites ls --region ${REGION}"
echo ""
echo "To run a test render:"
echo "  bash scripts/render-test.sh"
