export type KenBurnsType =
  | "zoom_in"
  | "zoom_out"
  | "pan_left"
  | "pan_right"
  | "pan_up"
  | "pan_down";

export interface CaptionWord {
  text: string;
  startFrame: number;
  endFrame: number;
  isHighlighted: boolean;
}

export interface SceneProps {
  imageUrl: string;
  startFrame: number;
  durationFrames: number;
  kenBurnsType: KenBurnsType;
  narrationText: string;
}

export interface VideoProps {
  title: string;
  scenes: SceneProps[];
  captionWords: CaptionWord[];
  audioUrl: string;
  musicUrl: string;
  totalDurationFrames: number;
  fps: number;
}
