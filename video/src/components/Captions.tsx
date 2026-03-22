import { AbsoluteFill, useCurrentFrame } from "remotion";
import { loadFont, fontFamily } from "@remotion/google-fonts/Montserrat";
import type { CaptionWord } from "../types";

// Load Montserrat Bold (weight 700) for captions
loadFont("normal", { weights: ["700"], subsets: ["latin"] });

const PHRASE_SIZE = 6; // 5-7 words per visible block

interface CaptionsProps {
  words: CaptionWord[];
}

/**
 * Renders animated word-by-word captions with phrase grouping.
 *
 * - Montserrat Bold via @remotion/google-fonts
 * - 5-7 word phrase blocks
 * - Yellow highlight on the active word
 * - Black outline (stroke) + drop shadow on white text
 * - Positioned above the YouTube progress bar (~bottom 15%)
 */
export const Captions: React.FC<CaptionsProps> = ({ words }) => {
  const frame = useCurrentFrame();

  // Find the currently active word (the one the viewer is hearing)
  const activeIndex = words.findIndex(
    (w) => frame >= w.startFrame && frame <= w.endFrame,
  );
  if (activeIndex === -1) return null;

  // Build a phrase window of PHRASE_SIZE words centered around the active word
  const phraseStart = Math.max(
    0,
    Math.min(
      activeIndex - Math.floor(PHRASE_SIZE / 2),
      words.length - PHRASE_SIZE,
    ),
  );
  const phraseEnd = Math.min(phraseStart + PHRASE_SIZE, words.length);
  const phraseWords = words.slice(phraseStart, phraseEnd);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: "15%", // above YouTube progress bar
      }}
    >
      <div
        style={{
          maxWidth: "80%",
          textAlign: "center",
          lineHeight: 1.4,
        }}
      >
        {phraseWords.map((word, i) => {
          const isActive =
            frame >= word.startFrame && frame <= word.endFrame;

          return (
            <span
              key={phraseStart + i}
              style={{
                color: isActive ? "#FFFF00" : "#FFFFFF",
                fontSize: 48,
                fontWeight: 700,
                fontFamily: `${fontFamily}, sans-serif`,
                marginRight: 10,
                // Black outline via text-stroke + drop shadow
                WebkitTextStroke: "2px #000000",
                textShadow:
                  "0 0 8px rgba(0,0,0,0.9), 0 4px 6px rgba(0,0,0,0.7)",
              }}
            >
              {word.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
