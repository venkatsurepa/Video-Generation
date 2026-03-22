import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  useCurrentFrame,
} from "remotion";
import type { CaptionWord, KenBurnsType, ShortProps } from "./types";
// fps is accessed via useVideoConfig(), not component props — see types.ts

// ---------------------------------------------------------------------------
// Aggressive Ken Burns — faster zoom/pan for Shorts' short durations
// ---------------------------------------------------------------------------

/**
 * Returns a CSS transform for Shorts-specific Ken Burns. More aggressive than
 * documentary preset: 1.0→1.25 scale, ±8% pan.
 *
 * @param type - One of 6 Ken Burns motion presets
 * @param progress - Animation progress from 0 (start) to 1 (end)
 */
function getShortKenBurnsTransform(
  type: KenBurnsType,
  progress: number,
): string {
  const lerp = (a: number, b: number) => a + (b - a) * progress;

  switch (type) {
    case "zoom_in": {
      const scale = lerp(1.0, 1.25);
      return `scale(${scale})`;
    }
    case "zoom_out": {
      const scale = lerp(1.25, 1.0);
      return `scale(${scale})`;
    }
    case "pan_left": {
      const x = lerp(8, -8);
      return `scale(1.15) translateX(${x}%)`;
    }
    case "pan_right": {
      const x = lerp(-8, 8);
      return `scale(1.15) translateX(${x}%)`;
    }
    case "pan_up": {
      const y = lerp(8, -8);
      return `scale(1.15) translateY(${y}%)`;
    }
    case "pan_down": {
      const y = lerp(-8, 8);
      return `scale(1.15) translateY(${y}%)`;
    }
    default: {
      const exhaustive: never = type;
      throw new Error(`Unknown Ken Burns type: ${exhaustive}`);
    }
  }
}

// ---------------------------------------------------------------------------
// Short Scene — image with aggressive Ken Burns
// ---------------------------------------------------------------------------

/** Renders a single Short scene image with aggressive Ken Burns motion. */
const ShortSceneView: React.FC<{
  imageUrl: string;
  durationFrames: number;
  kenBurnsType: KenBurnsType;
}> = ({ imageUrl, durationFrames, kenBurnsType }) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, durationFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const transform = getShortKenBurnsTransform(kenBurnsType, progress);

  return (
    <AbsoluteFill style={{ transform, willChange: "transform" }}>
      <Img
        src={imageUrl}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Captions — centered at 60% height, bold white with black outline
// ---------------------------------------------------------------------------

/** Renders word-level captions with gold highlight for emphasized words. */
const ShortCaptions: React.FC<{ words: CaptionWord[] }> = ({ words }) => {
  const frame = useCurrentFrame();

  const visibleWords = words.filter(
    (w) => frame >= w.startFrame && frame <= w.endFrame,
  );

  if (visibleWords.length === 0) return null;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        // Position at 60% from top (vertical center of lower portion)
        paddingTop: "20%",
      }}
    >
      <div
        style={{
          maxWidth: "90%",
          textAlign: "center",
          lineHeight: 1.4,
        }}
      >
        {visibleWords.map((word, i) => (
          <span
            key={i}
            style={{
              color: word.isHighlighted ? "#FFD700" : "#FFFFFF",
              fontSize: 56,
              fontWeight: 800,
              fontFamily: "Inter, sans-serif",
              marginRight: 10,
              textShadow:
                "-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000, 0 0 8px rgba(0,0,0,0.8)",
            }}
          >
            {word.text}
          </span>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Hook text overlay — first 1-2 seconds, fade in/out
// ---------------------------------------------------------------------------

/** Full-screen hook text overlay with fade in/out and scale entrance. */
const HookOverlay: React.FC<{
  text: string;
  durationFrames: number;
}> = ({ text, durationFrames }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(
    frame,
    [0, 8, durationFrames - 8, durationFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const scale = interpolate(frame, [0, 10], [0.9, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        backgroundColor: "rgba(0, 0, 0, 0.6)",
        opacity,
      }}
    >
      <div
        style={{
          maxWidth: "85%",
          textAlign: "center",
          transform: `scale(${scale})`,
        }}
      >
        <p
          style={{
            color: "#FFFFFF",
            fontSize: 64,
            fontWeight: 900,
            fontFamily: "Inter, sans-serif",
            lineHeight: 1.2,
            textShadow: "0 4px 12px rgba(0,0,0,0.8)",
            margin: 0,
          }}
        >
          {text}
        </p>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Cliffhanger end card — last 3-5 seconds
// ---------------------------------------------------------------------------

/** End card with cliffhanger text and pulsing "Watch full video" CTA. */
const CliffhangerCard: React.FC<{
  text: string;
  durationFrames: number;
}> = ({ text, durationFrames }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  const translateY = interpolate(frame, [0, 15], [30, 0], {
    extrapolateRight: "clamp",
  });

  // Pulsing "Watch full video" CTA
  const ctaOpacity = interpolate(
    frame,
    [25, 35, durationFrames - 10, durationFrames],
    [0, 1, 1, 0.7],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "rgba(0, 0, 0, 0.85)",
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <div
        style={{
          maxWidth: "85%",
          textAlign: "center",
          transform: `translateY(${translateY}px)`,
        }}
      >
        <p
          style={{
            color: "#FFFFFF",
            fontSize: 52,
            fontWeight: 800,
            fontFamily: "Inter, sans-serif",
            lineHeight: 1.3,
            textShadow: "0 2px 8px rgba(0,0,0,0.6)",
            margin: 0,
            marginBottom: 40,
          }}
        >
          {text}
        </p>
        <p
          style={{
            color: "#FF0000",
            fontSize: 36,
            fontWeight: 700,
            fontFamily: "Inter, sans-serif",
            opacity: ctaOpacity,
            margin: 0,
          }}
        >
          Watch the full video →
        </p>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Main CrimeShort composition
// ---------------------------------------------------------------------------

/** 9:16 YouTube Short composition — 1080×1920, 30fps, 13s or 60s. */
export const CrimeShort: React.FC<ShortProps> = ({
  scenes,
  captionWords,
  audioUrl,
  hookText,
  cliffhangerText,
  totalDurationFrames,
}) => {
  // Hook overlay: first 45 frames (1.5s)
  const hookDuration = 45;
  // Cliffhanger end card: last 120 frames (4s)
  const cliffhangerDuration = 120;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Scene images with Ken Burns */}
      {scenes.map((scene, i) => (
        <Sequence
          key={i}
          from={scene.startFrame}
          durationInFrames={scene.durationFrames}
        >
          <ShortSceneView
            imageUrl={scene.imageUrl}
            durationFrames={scene.durationFrames}
            kenBurnsType={scene.kenBurnsType}
          />
        </Sequence>
      ))}

      {/* Captions overlay — full duration */}
      <Sequence durationInFrames={totalDurationFrames}>
        <ShortCaptions words={captionWords} />
      </Sequence>

      {/* Hook text overlay — first 1.5 seconds */}
      {hookText && (
        <Sequence durationInFrames={hookDuration}>
          <HookOverlay text={hookText} durationFrames={hookDuration} />
        </Sequence>
      )}

      {/* Cliffhanger end card — last 4 seconds */}
      {cliffhangerText && (
        <Sequence
          from={totalDurationFrames - cliffhangerDuration}
          durationInFrames={cliffhangerDuration}
        >
          <CliffhangerCard
            text={cliffhangerText}
            durationFrames={cliffhangerDuration}
          />
        </Sequence>
      )}

      {/* Voiceover only — NO music (halves revenue) */}
      {audioUrl && <Audio src={audioUrl} />}
    </AbsoluteFill>
  );
};
