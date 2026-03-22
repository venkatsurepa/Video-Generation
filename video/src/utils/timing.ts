/**
 * Convert seconds to frames at the given FPS.
 *
 * @param seconds - Duration in seconds
 * @param fps - Frames per second
 */
export function secondsToFrames(seconds: number, fps: number): number {
  return Math.round(seconds * fps);
}

/**
 * Convert frames to seconds at the given FPS.
 *
 * @param frames - Number of frames
 * @param fps - Frames per second
 */
export function framesToSeconds(frames: number, fps: number): number {
  return frames / fps;
}

/**
 * Calculate total video duration in frames from scene durations in seconds.
 * Includes title card and end screen durations.
 *
 * @param sceneDurations - Array of scene durations in seconds
 * @param fps - Frames per second
 * @param titleSeconds - Title card duration in seconds (default: 3)
 * @param endScreenSeconds - End screen duration in seconds (default: 5)
 */
export function totalDurationFrames(
  sceneDurations: number[],
  fps: number,
  titleSeconds: number = 3,
  endScreenSeconds: number = 5,
): number {
  const scenesTotal = sceneDurations.reduce((sum, d) => sum + d, 0);
  return secondsToFrames(scenesTotal + titleSeconds + endScreenSeconds, fps);
}
