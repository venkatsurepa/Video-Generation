import { AbsoluteFill, Audio, Sequence, useVideoConfig } from "remotion";
import { Captions } from "./components/Captions";
import { EndScreen } from "./components/EndScreen";
import { Scene } from "./components/Scene";
import { TitleCard } from "./components/TitleCard";
import { Transition } from "./components/Transition";
import type { VideoProps } from "./types";
import { secondsToFrames } from "./utils/timing";

/**
 * Main CrimeDocumentary composition — 16:9 landscape, 2560×1440.
 *
 * Assembles title card, scenes with 0.5s crossfade transitions, captions overlay,
 * end screen CTA, and audio tracks (voiceover + background music).
 *
 * @param title - Video title displayed on the opening title card
 * @param scenes - Ordered scene list with images, timing, and Ken Burns presets
 * @param captionWords - Word-level caption timings for animated subtitle overlay
 * @param audioUrl - Voiceover audio URL (R2 signed URL)
 * @param musicUrl - Background music URL (R2 signed URL), played at 15% volume
 * @param totalDurationFrames - Total scene duration in frames (excludes title card)
 */
export const CrimeDocumentary: React.FC<VideoProps> = ({
  title,
  scenes,
  captionWords,
  audioUrl,
  musicUrl,
  totalDurationFrames,
}) => {
  const { fps } = useVideoConfig();
  const titleDuration = secondsToFrames(3, fps);
  const endScreenDuration = secondsToFrames(5, fps);
  const crossfadeFrames = secondsToFrames(0.5, fps);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Title card */}
      <Sequence durationInFrames={titleDuration}>
        <TitleCard title={title} durationFrames={titleDuration} />
      </Sequence>

      {/* Scenes with crossfade transitions — each scene lingers for crossfadeFrames
          while the next fades in on top, creating a dissolve effect. */}
      {scenes.map((scene, i) => {
        const isLast = i === scenes.length - 1;
        return (
          <Sequence
            key={i}
            from={titleDuration + scene.startFrame}
            durationInFrames={
              scene.durationFrames + (isLast ? 0 : crossfadeFrames)
            }
          >
            {i > 0 ? (
              <Transition type="fade" durationFrames={crossfadeFrames}>
                <Scene {...scene} />
              </Transition>
            ) : (
              <Scene {...scene} />
            )}
          </Sequence>
        );
      })}

      {/* Captions overlay — offset by titleDuration to match scene timing */}
      <Sequence from={titleDuration} durationInFrames={totalDurationFrames}>
        <Captions words={captionWords} />
      </Sequence>

      {/* End screen */}
      <Sequence
        from={titleDuration + totalDurationFrames - endScreenDuration}
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
