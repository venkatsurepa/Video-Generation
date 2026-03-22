import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

/**
 * Renders an end screen with "Thanks for watching" and subscribe CTA.
 * Fades in over 20 frames with semi-transparent dark background overlay.
 */
export const EndScreen: React.FC = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "rgba(0, 0, 0, 0.85)",
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <div style={{ textAlign: "center" }}>
        <p
          style={{
            color: "#FFFFFF",
            fontSize: 48,
            fontWeight: 700,
            fontFamily: "Inter, sans-serif",
            marginBottom: 20,
          }}
        >
          Thanks for watching
        </p>
        <p
          style={{
            color: "#FF0000",
            fontSize: 32,
            fontWeight: 600,
            fontFamily: "Inter, sans-serif",
          }}
        >
          SUBSCRIBE for more
        </p>
      </div>
    </AbsoluteFill>
  );
};
