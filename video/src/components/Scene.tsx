import { AbsoluteFill, Img } from "remotion";
import type { SceneProps } from "../types";
import { KenBurns } from "./KenBurns";

/** Renders a single scene with a Ken Burns effect on the image. */
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
