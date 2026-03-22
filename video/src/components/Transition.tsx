import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

interface TransitionProps {
  type: "fade" | "wipe_left";
  durationFrames: number;
  children: React.ReactNode;
}

/**
 * Applies an entrance transition effect to its children.
 * Used for crossfade transitions between scenes (0.5s fade-in).
 *
 * @param type - Transition style: "fade" (opacity 0→1) or "wipe_left" (slide in)
 * @param durationFrames - How many frames the transition takes to complete
 * @param children - Content to animate in
 */
export const Transition: React.FC<TransitionProps> = ({
  type,
  durationFrames,
  children,
}) => {
  const frame = useCurrentFrame();

  if (type === "fade") {
    const opacity = interpolate(frame, [0, durationFrames], [0, 1], {
      extrapolateRight: "clamp",
    });
    return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
  }

  // wipe_left
  const translateX = interpolate(frame, [0, durationFrames], [100, 0], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ transform: `translateX(${translateX}%)` }}>
      {children}
    </AbsoluteFill>
  );
};
