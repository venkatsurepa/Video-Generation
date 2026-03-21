import { AbsoluteFill, Audio, Sequence } from "remotion";
import { Captions } from "./components/Captions";
import { EndScreen } from "./components/EndScreen";
import { Scene } from "./components/Scene";
import { TitleCard } from "./components/TitleCard";
import type { VideoProps } from "./types";

/** Main composition that assembles all scenes with audio and captions. */
export const CrimeDocumentary: React.FC<VideoProps> = ({
  title,
  scenes,
  captionWords,
  audioUrl,
  musicUrl,
  totalDurationFrames,
}) => {
  const titleDuration = 90; // 3 seconds at 30fps
  const endScreenDuration = 150; // 5 seconds

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Title card */}
      <Sequence durationInFrames={titleDuration}>
        <TitleCard title={title} durationFrames={titleDuration} />
      </Sequence>

      {/* Scenes */}
      {scenes.map((scene, i) => (
        <Sequence
          key={i}
          from={scene.startFrame}
          durationInFrames={scene.durationFrames}
        >
          <Scene {...scene} />
        </Sequence>
      ))}

      {/* Captions overlay */}
      <Sequence durationInFrames={totalDurationFrames}>
        <Captions words={captionWords} />
      </Sequence>

      {/* End screen */}
      <Sequence
        from={totalDurationFrames - endScreenDuration}
        durationInFrames={endScreenDuration}
      >
        <EndScreen />
      </Sequence>

      {/* Audio tracks */}
      {audioUrl && <Audio src={audioUrl} />}
      {musicUrl && <Audio src={musicUrl} volume={0.15} />}
    </AbsoluteFill>
  );
};
