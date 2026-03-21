import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

interface TransitionProps {
  type: "fade" | "wipe_left";
  durationFrames: number;
  children: React.ReactNode;
}

/** Applies an entrance transition effect to its children. */
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
