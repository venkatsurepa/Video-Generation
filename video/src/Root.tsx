import { Composition } from "remotion";
import { CrimeDocumentary } from "./CrimeDocumentary";
import { CrimeShort } from "./CrimeShort";
import type { ShortProps, VideoProps } from "./types";
import { secondsToFrames } from "./utils/timing";

/*
 * Remotion 4 Composition requires Props extends Record<string, unknown>.
 * Our typed interfaces don't have an index signature, so we widen via `any`.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const DocComp = CrimeDocumentary as React.FC<any>;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ShortComp = CrimeShort as React.FC<any>;

/** Default frame rate for all compositions. */
const DEFAULT_FPS = 30;
/** Title card duration in seconds (converted to frames via {@link secondsToFrames}). */
const TITLE_SECONDS = 3;

/**
 * Root component — registers CrimeDocumentary and CrimeShort compositions.
 *
 * fps is intentionally kept here (not in component props) because frame-based
 * timing in components is fps-independent. Components access fps via
 * `useVideoConfig()` when they need it for seconds-to-frames conversion.
 */
export const Root: React.FC = () => {
  const defaultProps: VideoProps = {
    title: "",
    scenes: [],
    captionWords: [],
    audioUrl: "",
    musicUrl: "",
    totalDurationFrames: 900,
  };

  const defaultShortProps: ShortProps = {
    scenes: [],
    captionWords: [],
    audioUrl: "",
    hookText: "",
    cliffhangerText: "",
    totalDurationFrames: 390,
  };

  return (
    <>
      <Composition
        id="CrimeDocumentary"
        component={DocComp}
        durationInFrames={
          defaultProps.totalDurationFrames +
          secondsToFrames(TITLE_SECONDS, DEFAULT_FPS)
        }
        fps={DEFAULT_FPS}
        width={2560}
        height={1440}
        defaultProps={defaultProps}
        calculateMetadata={({ props }) => ({
          durationInFrames:
            Number(props.totalDurationFrames) +
            secondsToFrames(TITLE_SECONDS, DEFAULT_FPS),
          fps: DEFAULT_FPS,
        })}
      />
      <Composition
        id="CrimeShort"
        component={ShortComp}
        durationInFrames={defaultShortProps.totalDurationFrames}
        fps={DEFAULT_FPS}
        width={1080}
        height={1920}
        defaultProps={defaultShortProps}
        calculateMetadata={({ props }) => ({
          durationInFrames: Number(props.totalDurationFrames),
          fps: DEFAULT_FPS,
        })}
      />
    </>
  );
};
