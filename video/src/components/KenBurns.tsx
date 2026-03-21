import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import type { KenBurnsType } from "../types";
import { getKenBurnsTransform } from "../utils/kenburns";

interface KenBurnsProps {
  type: KenBurnsType;
  durationFrames: number;
  children: React.ReactNode;
}

/** Applies a Ken Burns (pan/zoom) animation to its children over the given duration. */
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
