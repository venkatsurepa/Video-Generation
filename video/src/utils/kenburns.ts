import type { KenBurnsType } from "../types";

const ALL_TYPES: KenBurnsType[] = [
  "zoom_in",
  "zoom_out",
  "pan_left",
  "pan_right",
  "pan_up",
  "pan_down",
];

/**
 * Returns the next Ken Burns type, guaranteed to never repeat the previous type.
 * Cycles through all 6 presets in a deterministic order, skipping if it would
 * be the same as `previous`.
 *
 * @param previous - The Ken Burns type used on the preceding scene, or null for first scene
 * @param index - Scene index in the video, used to cycle through presets
 */
export function getNextKenBurnsType(
  previous: KenBurnsType | null,
  index: number = 0,
): KenBurnsType {
  let candidate = ALL_TYPES[index % ALL_TYPES.length];
  if (candidate === previous) {
    candidate = ALL_TYPES[(index + 1) % ALL_TYPES.length];
  }
  return candidate;
}

/**
 * Returns a CSS transform string for the given Ken Burns effect type and progress.
 * Documentary preset: 1.0→1.15 scale, ±5% pan.
 *
 * @param type - One of 6 Ken Burns motion presets
 * @param progress - Animation progress from 0 (start) to 1 (end)
 */
export function getKenBurnsTransform(
  type: KenBurnsType,
  progress: number,
): string {
  const lerp = (a: number, b: number) => a + (b - a) * progress;

  switch (type) {
    case "zoom_in": {
      const scale = lerp(1.0, 1.15);
      return `scale(${scale})`;
    }
    case "zoom_out": {
      const scale = lerp(1.15, 1.0);
      return `scale(${scale})`;
    }
    case "pan_left": {
      const x = lerp(5, -5);
      return `scale(1.1) translateX(${x}%)`;
    }
    case "pan_right": {
      const x = lerp(-5, 5);
      return `scale(1.1) translateX(${x}%)`;
    }
    case "pan_up": {
      const y = lerp(5, -5);
      return `scale(1.1) translateY(${y}%)`;
    }
    case "pan_down": {
      const y = lerp(-5, 5);
      return `scale(1.1) translateY(${y}%)`;
    }
    default: {
      const exhaustive: never = type;
      throw new Error(`Unknown Ken Burns type: ${exhaustive}`);
    }
  }
}
