import { AbsoluteFill, Img } from "remotion";
import type { SceneProps } from "../types";
import { KenBurns } from "./KenBurns";

/**
 * Renders a single scene with Ken Burns motion effect.
 * Images should be 10–15% larger than the output frame for cropping headroom.
 *
 * @param imageUrl - URL to the scene image (R2 signed URL)
 * @param durationFrames - How long this scene displays, in frames
 * @param kenBurnsType - One of 6 motion presets, should not repeat consecutively
 */
export const Scene: React.FC<SceneProps> = ({
  imageUrl,
  durationFrames,
  kenBurnsType,
}) => {
  return (
    <AbsoluteFill>
      <KenBurns type={kenBurnsType} durationFrames={durationFrames}>
        <Img
          src={imageUrl}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </KenBurns>
    </AbsoluteFill>
  );
};
