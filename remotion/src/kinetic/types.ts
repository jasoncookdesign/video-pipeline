// Mirrors video_pipeline.kinetic.props.kinetic_to_remotion_props (schemaVersion 3)
// and schema/kinetic.schema.json. The Python boundary validates everything and
// resolves every word's style and timing before a render, so components trust
// these shapes and do no text analysis or timing arithmetic.
import type { Box, VisualStyle } from "../visuals/types";

export type Role = "statement" | "aside" | "question";
export type Motion = "resolve" | "rise" | "slide" | "mask" | "gather" | "diminish";
export type Slot = "top" | "middle" | "bottom";
export type Align = "left" | "center" | "right";
export type WordColor = "text" | "accent" | "warm" | "dim";
export type Treatment = "none" | "whip" | "bloom" | "swell";

export type WordPlan = {
  text: string;
  family: "display" | "body";
  weight: number;
  italic: boolean;
  scale: number;
  color: WordColor;
  treatment: Treatment;
  keep: boolean; // no line break after this word
  inFrom: number; // frames from the beat's start
  inFrames: number;
  outFrom: number;
  outFrames: number; // 0 = holds to the end of the layer
  treatFrom: number;
  treatFrames: number; // 0 = no treatment
  line: number; // 0-based line the word sits on (decided in Python)
  pushes: [number, number, number][]; // [from frame, frames, px]: slides over as an earlier whip leans
};

export type TextBeat = {
  id: string;
  kind: "text";
  from: number;
  durationInFrames: number;
  holdToEnd: boolean;
  text: string;
  role: Role;
  motion: Motion;
  slot: Slot;
  align: Align;
  sizePx: number;
  revealFrames: number;
  exitFrames: number;
  driftPx: number;
  lineHeights: number[]; // px, one per line
  blockHeight: number; // px
  words: WordPlan[];
};

export type SpaceBeat = { id: string; kind: "space"; from: number; durationInFrames: number; holdToEnd: boolean };
export type KineticBeat = TextBeat | SpaceBeat;

export type KineticProps = {
  schemaVersion: number;
  kind: "kinetic";
  reelId: string;
  fps: number;
  durationInFrames: number;
  dimensions: { width: number; height: number };
  safeBox: Box;
  titleBox: Box;
  bodyBox: Box;
  bodyContainer: Box; // as tall as the tallest block, at the bottom of the safe zone
  style: VisualStyle;
  minType: { label_px: number; body_px: number; heading_px: number; title_px: number };
  title: string;
  titlePx: number; // fitted in Python from measured glyph widths
  beats: KineticBeat[];
};
