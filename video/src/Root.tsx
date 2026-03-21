import { Composition } from "remotion";
import { CrimeDocumentary } from "./CrimeDocumentary";
import type { VideoProps } from "./types";

export const Root: React.FC = () => {
  const defaultProps: VideoProps = {
    title: "",
    scenes: [],
    captionWords: [],
    audioUrl: "",
    musicUrl: "",
    totalDurationFrames: 900,
    fps: 30,
  };

  return (
    <Composition
      id="CrimeDocumentary"
      component={CrimeDocumentary}
      durationInFrames={defaultProps.totalDurationFrames}
      fps={defaultProps.fps}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
    />
  );
};
