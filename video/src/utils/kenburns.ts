import type { KenBurnsType } from "../types";

/**
 * Returns a CSS transform string for the given Ken Burns effect type and progress (0-1).
 * The transform starts at the "from" state and ends at the "to" state.
 */
export function getKenBurnsTransform(
  type: KenBurnsType,
  progress: number
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
  }
}
