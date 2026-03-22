import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { KenBurnsType } from "../types";
import { getKenBurnsTransform } from "../utils/kenburns";

interface KenBurnsProps {
  type: KenBurnsType;
  durationFrames: number;
  children: React.ReactNode;
}

/**
 * Applies a Ken Burns (pan/zoom) animation to its children over the given duration.
 * Uses `getKenBurnsTransform` from utils for the CSS transform calculation.
 *
 * @param type - One of 6 motion presets (zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down)
 * @param durationFrames - Total animation duration in frames
 * @param children - Content to apply the Ken Burns effect to (typically an Img)
 */
export const KenBurns: React.FC<KenBurnsProps> = ({
  type,
  durationFrames,
  children,
}) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, durationFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const transform = getKenBurnsTransform(type, progress);

  return (
    <AbsoluteFill style={{ transform, willChange: "transform" }}>
      {children}
    </AbsoluteFill>
  );
};
