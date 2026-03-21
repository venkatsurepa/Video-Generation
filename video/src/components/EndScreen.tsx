import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

/** Renders an end screen with subscribe CTA and fade-in. */
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
