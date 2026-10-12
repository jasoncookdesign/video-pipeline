// Mirrors video_pipeline.visuals.props.beat_to_remotion_props (schemaVersion 1)
// and the per-template props contracts in schema/visuals.schema.json. The Python
// boundary validates everything before a render, so components trust these shapes.

export type Box = { x: number; y: number; width: number; height: number };

export type VisualStyle = {
  ground: string;
  surface: string;
  surface_2: string;
  line: string;
  line_2: string;
  text: string;
  text_2: string;
  accent: string;
  accent_ink: string;
  warm: string;
  alert: string;
  display_font: string;
  body_font: string;
  mono_font: string;
  label_px: number;
  body_px: number;
  heading_px: number;
  title_px: number;
  parody_label: string;
  brand_label: string;
};

export type TextCardProps = {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  source?: string;
};

export type GameHudProps = {
  title: string;
  currency?: { label: string; value: number };
  stack?: { label: string; items: string[] };
  achievement?: { label: string; state: "locked" | "unlocked" };
  toast?: string;
};

export type StoreCardProps = {
  eyebrow?: string;
  title: string;
  price: string;
  price_note?: string;
  features?: string[];
  cta: string;
  badge?: string;
};

export type Stat = {
  label: string;
  value: number;
  from?: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
};

export type StatDashboardProps = { title: string; stats: Stat[]; footnote?: string };

export type ProgressBarProps = {
  label: string;
  from_pct?: number;
  to_pct: number;
  status?: string;
  caption?: string;
};

export type TimelineProps = {
  title?: string;
  items: { when?: string; label: string }[];
  emphasis_last?: boolean;
};

export type FlowchartProps = { title?: string; steps: string[] };

export type TemplateProps =
  | TextCardProps
  | GameHudProps
  | StoreCardProps
  | StatDashboardProps
  | ProgressBarProps
  | TimelineProps
  | FlowchartProps;

export type VisualProps<P = TemplateProps> = {
  schemaVersion: number;
  kind: "visual";
  template: string;
  reelId: string;
  beatId: string;
  layout: "split" | "full-graphic";
  parody: boolean;
  fps: number;
  beatFrames: number; // the beat itself; the clip adds a held tail
  durationInFrames: number;
  dimensions: { width: number; height: number };
  safeBox: Box; // content rect, relative to this clip's frame
  style: VisualStyle;
  // legibility floors (px) from video_pipeline.visuals.style.MIN_TYPE_PX:
  // fitted text may shrink toward these, never below
  minType: { label_px: number; body_px: number; heading_px: number; title_px: number };
  props: P;
};
