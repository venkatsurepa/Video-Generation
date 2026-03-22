#!/usr/bin/env bash
# ============================================================
# Test Remotion Lambda render with sample input props
# ============================================================
# Requires REMOTION_LAMBDA_FUNCTION_NAME and REMOTION_SERVE_URL
# to be set in the environment (from deploy-lambda.sh output).
# ============================================================

set -euo pipefail

REGION="${REMOTION_AWS_REGION:-us-east-1}"

if [ -z "${REMOTION_LAMBDA_FUNCTION_NAME:-}" ]; then
  echo "ERROR: REMOTION_LAMBDA_FUNCTION_NAME is not set"
  echo "Run deploy-lambda.sh first, then export the function name."
  exit 1
fi

if [ -z "${REMOTION_SERVE_URL:-}" ]; then
  echo "ERROR: REMOTION_SERVE_URL is not set"
  echo "Run deploy-lambda.sh first, then export the serve URL."
  exit 1
fi

cd "$(dirname "$0")/.."

echo "=== CrimeMill Test Render ==="
echo "Function: ${REMOTION_LAMBDA_FUNCTION_NAME}"
echo "Serve URL: ${REMOTION_SERVE_URL}"
echo "Region: ${REGION}"
echo ""

# Use sample-props.json for a realistic test (3 scenes, 10 seconds)
if [ -f "sample-props.json" ]; then
  echo "Using sample-props.json..."
  PROPS_FILE="sample-props.json"
else
  echo "sample-props.json not found, using minimal inline props..."
  PROPS_FILE=""
fi

if [ -n "${PROPS_FILE}" ]; then
  npx remotion lambda render \
    "${REMOTION_SERVE_URL}" \
    CrimeDocumentary \
    --function-name "${REMOTION_LAMBDA_FUNCTION_NAME}" \
    --props "$(cat "${PROPS_FILE}")" \
    --region "${REGION}"
else
  npx remotion lambda render \
    "${REMOTION_SERVE_URL}" \
    CrimeDocumentary \
    --function-name "${REMOTION_LAMBDA_FUNCTION_NAME}" \
    --props '{"title":"Test Render","scenes":[],"captionWords":[],"audioUrl":"","musicUrl":"","totalDurationFrames":300,"fps":30}' \
    --region "${REGION}"
fi

echo ""
echo "=== Test Render Complete ==="
