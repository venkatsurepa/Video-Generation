/** Ken Burns animation preset — controls camera movement on scene images. */
export type KenBurnsType =
  | "zoom_in"
  | "zoom_out"
  | "pan_left"
  | "pan_right"
  | "pan_up"
  | "pan_down";

/** A single word in the caption track with frame-level timing. */
export interface CaptionWord {
  /** The word text to display. */
  text: string;
  /** Frame at which this word starts being spoken. */
  startFrame: number;
  /** Frame at which this word finishes being spoken. */
  endFrame: number;
  /** Whether to visually emphasize this word (gold/yellow highlight). */
  isHighlighted: boolean;
}

/**
 * A single scene in the documentary — one image with Ken Burns animation.
 * Images should be 10–15% larger than the output frame for cropping headroom.
 */
export interface SceneProps {
  /** URL to the scene image (R2 signed URL). */
  imageUrl: string;
  /** Frame offset at which this scene appears (relative to scene timeline). */
  startFrame: number;
  /** How long this scene displays, in frames. */
  durationFrames: number;
  /** One of 6 motion presets — should not repeat consecutively. */
  kenBurnsType: KenBurnsType;
  /** Narration text for this scene (used by assembler, not rendered directly). */
  narrationText: string;
}

/**
 * Props for the CrimeDocumentary composition (16:9 landscape, 2560×1440).
 *
 * fps is intentionally excluded — frame-based timing is fps-independent.
 * Components use `useVideoConfig()` when they need fps for conversions.
 */
export interface VideoProps {
  /** Video title displayed on the opening title card. */
  title: string;
  /** Ordered scene list with images, timing, and Ken Burns presets. */
  scenes: SceneProps[];
  /** Word-level caption timings for animated subtitle overlay. */
  captionWords: CaptionWord[];
  /** Voiceover audio URL (R2 signed URL). */
  audioUrl: string;
  /** Background music URL (R2 signed URL), played at 15% volume. */
  musicUrl: string;
  /** Total scene duration in frames (excludes title card and end screen). */
  totalDurationFrames: number;
}

// ---------------------------------------------------------------------------
// Shorts (9:16, 1080×1920)
// ---------------------------------------------------------------------------

/** A single scene in a YouTube Short — image with aggressive Ken Burns. */
export interface ShortScene {
  /** URL to the scene image (R2 signed URL, 1080×1920). */
  imageUrl: string;
  /** Frame offset at which this scene appears. */
  startFrame: number;
  /** How long this scene displays, in frames. */
  durationFrames: number;
  /** One of 6 motion presets — more aggressive than documentary (1.25× vs 1.15×). */
  kenBurnsType: KenBurnsType;
}

/**
 * Props for the CrimeShort composition (9:16 vertical, 1080×1920).
 *
 * fps is intentionally excluded — see {@link VideoProps} for rationale.
 */
export interface ShortProps {
  /** Scene list covering the full short duration. */
  scenes: ShortScene[];
  /** Word-level caption timings. */
  captionWords: CaptionWord[];
  /** Voiceover audio URL. No background music (halves ad revenue on Shorts). */
  audioUrl: string;
  /** Bold hook text displayed in the first 1.5 seconds. */
  hookText: string;
  /** Teaser text for the full video, shown in the last 4 seconds. */
  cliffhangerText: string;
  /** Total duration in frames. */
  totalDurationFrames: number;
}
