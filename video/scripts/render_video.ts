/**
 * Node.js bridge script for Remotion Lambda rendering.
 *
 * Called by the Python backend (VideoAssembler) to trigger and monitor
 * Remotion Lambda renders. This script bridges Python → @remotion/lambda
 * since the Remotion Lambda SDK is Node.js-only.
 *
 * Usage:
 *   # Trigger a render (reads input props JSON from stdin):
 *   echo '{"title": "...", ...}' | npx tsx scripts/render_video.ts
 *   → stdout: {"renderId": "abc123", "bucketName": "remotionlambda-..."}
 *
 *   # Check render status (--bucket recommended, otherwise falls back to convention):
 *   npx tsx scripts/render_video.ts --status <render_id> --bucket <bucket_name>
 *   → stdout: {"status": "done", "progress": 1.0, "outputUrl": "https://..."}
 *
 * Environment variables (set by VideoAssembler):
 *   REMOTION_AWS_ACCESS_KEY_ID      — IAM key with Lambda + S3 permissions
 *   REMOTION_AWS_SECRET_ACCESS_KEY  — corresponding secret
 *   REMOTION_AWS_REGION             — e.g. us-east-1
 *   REMOTION_LAMBDA_FUNCTION_NAME   — deployed Lambda function name
 *   REMOTION_SERVE_URL              — deployed Remotion site URL
 *   REMOTION_FRAMES_PER_LAMBDA      — frames per Lambda chunk (default: 20)
 *   REMOTION_RENDER_TIMEOUT_MS      — render timeout (default: 300000)
 *   RENDER_VIDEO_ID                 — video ID for output naming
 *   REMOTION_COMPOSITION            — composition ID (default: CrimeDocumentary)
 *   REMOTION_BUCKET_NAME            — S3 bucket for status checks (optional)
 */

import {
  renderMediaOnLambda,
  getRenderProgress,
  type AwsRegion,
} from "@remotion/lambda/client";

// ---------------------------------------------------------------------------
// Config from environment
// ---------------------------------------------------------------------------

const REGION = (process.env.REMOTION_AWS_REGION ?? "us-east-1") as AwsRegion;
const FUNCTION_NAME = process.env.REMOTION_LAMBDA_FUNCTION_NAME ?? "";
const SERVE_URL = process.env.REMOTION_SERVE_URL ?? "";
const FRAMES_PER_LAMBDA = parseInt(
  process.env.REMOTION_FRAMES_PER_LAMBDA ?? "20",
  10,
);
const RENDER_TIMEOUT_MS = parseInt(
  process.env.REMOTION_RENDER_TIMEOUT_MS ?? "300000",
  10,
);
const VIDEO_ID = process.env.RENDER_VIDEO_ID ?? "unknown";
const COMPOSITION = process.env.REMOTION_COMPOSITION ?? "CrimeDocumentary";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fatal(message: string): never {
  process.stderr.write(`ERROR: ${message}\n`);
  process.exit(1);
}

function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);

    // If stdin is a TTY (no pipe), bail
    if (process.stdin.isTTY) {
      fatal(
        "No input on stdin. Pipe input props JSON or use --status <render_id>.",
      );
    }
  });
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

async function triggerRender(): Promise<void> {
  if (!SERVE_URL) fatal("REMOTION_SERVE_URL is required");
  if (!FUNCTION_NAME) fatal("REMOTION_LAMBDA_FUNCTION_NAME is required");

  const raw = await readStdin();
  let inputProps: Record<string, unknown>;
  try {
    inputProps = JSON.parse(raw);
  } catch {
    fatal(`Invalid JSON on stdin: ${raw.substring(0, 200)}`);
  }

  process.stderr.write(
    `Triggering render for video ${VIDEO_ID} (${REGION})...\n`,
  );

  const { renderId, bucketName } = await renderMediaOnLambda({
    region: REGION,
    functionName: FUNCTION_NAME,
    serveUrl: SERVE_URL,
    composition: COMPOSITION,
    inputProps,
    codec: "h264",
    imageFormat: "jpeg",
    framesPerLambda: FRAMES_PER_LAMBDA,
    privacy: "no-acl",
    maxRetries: 2,
    timeoutInMilliseconds: RENDER_TIMEOUT_MS,
    outName: `${VIDEO_ID}.mp4`,
    downloadBehavior: { type: "play-in-browser" },
  });

  process.stderr.write(
    `Render started: ${renderId} (bucket: ${bucketName})\n`,
  );

  // Output result as JSON to stdout for the Python caller to parse
  process.stdout.write(
    JSON.stringify({ renderId, bucketName }) + "\n",
  );
}

async function checkStatus(
  renderId: string,
  bucketOverride?: string,
): Promise<void> {
  if (!FUNCTION_NAME) fatal("REMOTION_LAMBDA_FUNCTION_NAME is required");

  // Prefer explicit bucket from --bucket flag or env; fall back to convention
  const bucketName =
    bucketOverride ??
    process.env.REMOTION_BUCKET_NAME ??
    `remotionlambda-${REGION}`;

  const progress = await getRenderProgress({
    renderId,
    bucketName,
    region: REGION,
    functionName: FUNCTION_NAME,
  });

  if (progress.fatalErrorEncountered) {
    const errorMsg =
      progress.errors?.[0]?.message ?? "Unknown fatal error";
    process.stdout.write(
      JSON.stringify({
        status: "error",
        progress: progress.overallProgress ?? 0,
        errorMessage: errorMsg,
      }) + "\n",
    );
    return;
  }

  if (progress.done) {
    process.stdout.write(
      JSON.stringify({
        status: "done",
        progress: 1.0,
        outputUrl: progress.outputFile,
      }) + "\n",
    );
    return;
  }

  process.stdout.write(
    JSON.stringify({
      status: "rendering",
      progress: progress.overallProgress ?? 0,
    }) + "\n",
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const statusFlagIndex = process.argv.indexOf("--status");

  if (statusFlagIndex !== -1) {
    const renderId = process.argv[statusFlagIndex + 1];
    if (!renderId) fatal("--status requires a render ID argument");

    // Optional --bucket flag for explicit bucket name
    const bucketFlagIndex = process.argv.indexOf("--bucket");
    const bucketOverride =
      bucketFlagIndex !== -1 ? process.argv[bucketFlagIndex + 1] : undefined;

    await checkStatus(renderId, bucketOverride);
  } else {
    await triggerRender();
  }
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err}\n`);
  process.exit(1);
});
