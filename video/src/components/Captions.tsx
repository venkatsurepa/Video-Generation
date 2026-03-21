import { AbsoluteFill, useCurrentFrame } from "remotion";
import type { CaptionWord } from "../types";

interface CaptionsProps {
  words: CaptionWord[];
}

/** Renders animated word-by-word captions at the bottom of the frame. */
export const Captions: React.FC<CaptionsProps> = ({ words }) => {
  const frame = useCurrentFrame();

  const visibleWords = words.filter(
    (w) => frame >= w.startFrame && frame <= w.endFrame
  );

  if (visibleWords.length === 0) return null;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 80,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0, 0, 0, 0.7)",
          padding: "12px 24px",
          borderRadius: 8,
          maxWidth: "80%",
          textAlign: "center",
        }}
      >
        {visibleWords.map((word, i) => (
          <span
            key={i}
            style={{
              color: word.isHighlighted ? "#FFD700" : "#FFFFFF",
              fontSize: 42,
              fontWeight: word.isHighlighted ? 700 : 500,
              fontFamily: "Inter, sans-serif",
              marginRight: 8,
            }}
          >
            {word.text}
          </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};
