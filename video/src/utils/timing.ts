/** Convert seconds to frames at the given FPS. */
export function secondsToFrames(seconds: number, fps: number): number {
  return Math.round(seconds * fps);
}

/** Convert frames to seconds at the given FPS. */
export function framesToSeconds(frames: number, fps: number): number {
  return frames / fps;
}

/** Calculate total duration in frames from an array of scene durations in seconds. */
export function totalDurationFrames(
  sceneDurations: number[],
  fps: number,
  titleSeconds: number = 3,
  endScreenSeconds: number = 5
): number {
  const scenesTotal = sceneDurations.reduce((sum, d) => sum + d, 0);
  return secondsToFrames(scenesTotal + titleSeconds + endScreenSeconds, fps);
}
