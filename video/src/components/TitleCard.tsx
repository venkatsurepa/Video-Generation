import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

interface TitleCardProps {
  title: string;
  durationFrames: number;
}

/**
 * Renders a cinematic opening title card with fade in/out and subtle zoom.
 * White uppercase text on black background, Inter font weight 800.
 *
 * @param title - The video title to display
 * @param durationFrames - How long the title card is visible, in frames
 */
export const TitleCard: React.FC<TitleCardProps> = ({
  title,
  durationFrames,
}) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 20, durationFrames - 15, durationFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const scale = interpolate(frame, [0, durationFrames], [1.05, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#000",
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <h1
        style={{
          color: "#FFFFFF",
          fontSize: 72,
          fontWeight: 800,
          fontFamily: "Inter, sans-serif",
          textAlign: "center",
          maxWidth: "80%",
          textTransform: "uppercase",
          letterSpacing: 4,
          transform: `scale(${scale})`,
        }}
      >
        {title}
      </h1>
    </AbsoluteFill>
  );
};
