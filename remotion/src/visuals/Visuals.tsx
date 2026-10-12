// Registers one Remotion composition per visual template (#62). Composition ids
// mirror video_pipeline.visuals.props.TEMPLATE_COMPOSITIONS; calculateMetadata
// sizes every render to the clip's region and its beat-plus-hold length.
import React from "react";
import { Composition } from "remotion";
import { Flowchart, GameHud, ProgressBar, StatDashboard, StoreCard, TextCard, Timeline } from "./templates";
import type { VisualProps, VisualStyle } from "./types";

const previewStyle: VisualStyle = {
  ground: "#191919", surface: "#202020", surface_2: "#262626", line: "#343434", line_2: "#454545",
  text: "#EDEDED", text_2: "#9C9CA0", accent: "#9C97F4", accent_ink: "#141318", warm: "#E8B27C",
  alert: "#FF6B5A", display_font: "Archivo", body_font: "Inter", mono_font: "IBM Plex Mono",
  label_px: 30, body_px: 44, heading_px: 64, title_px: 112, parody_label: "PARODY",
  brand_label: "DYSON HOPE",
};

// Studio fallback props (a split-panel beat). Real renders pass --props.
const base = (template: string, props: unknown, parody = false): VisualProps<any> => ({
  schemaVersion: 1, kind: "visual", template, reelId: "PREVIEW", beatId: "B01",
  layout: "split", parody, fps: 30, beatFrames: 120, durationInFrames: 165,
  dimensions: { width: 1080, height: 960 }, safeBox: { x: 35, y: 250, width: 1010, height: 710 },
  style: previewStyle, props,
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const meta = ({ props }: { props: Record<string, unknown> }) => {
  const v = props as unknown as VisualProps<any>;
  return {
    durationInFrames: Math.max(1, v.durationInFrames),
    fps: v.fps,
    width: v.dimensions.width,
    height: v.dimensions.height,
  };
};

const TEMPLATES: [string, React.FC<any>, VisualProps<any>][] = [
  ["TextCard", TextCard, base("text-card", { eyebrow: "VIA MUSIC ALLY", title: "MUSIC FESTIVAL TYCOON", subtitle: "Live Nation × Livewire, on Roblox" })],
  ["GameHud", GameHud, base("game-hud", { title: "MUSIC FESTIVAL TYCOON", currency: { label: "COINS", value: 1250000 }, stack: { label: "WRISTBAND TIERS", items: ["GA", "VIP", "VIP+", "PLATINUM"] }, achievement: { label: "FREE PARTY", state: "locked" } }, true)],
  ["StoreCard", StoreCard, base("store-card", { eyebrow: "EXPANSION PACK", title: "WRISTBAND TIERS DLC", price: "$29.99", features: ["Six wristband tiers"], cta: "BUY NOW" }, true)],
  ["StatDashboard", StatDashboard, base("stat-dashboard", { title: "FESTIVAL KPIs", stats: [{ label: "Tickets sold", value: 48210 }, { label: "Dancefloor", value: 3, suffix: "%" }] }, true)],
  ["ProgressBar", ProgressBar, base("progress-bar", { label: "BUILDING YOUR SCENE", to_pct: 99, status: "Finding a borrowed room…" })],
  ["Timeline", Timeline, base("timeline", { title: "TICKET PRICES", items: [{ when: "08:00", label: "GA on sale" }, { when: "08:01", label: "GA sold out" }], emphasis_last: true }, true)],
  ["Flowchart", Flowchart, base("flowchart", { steps: ["Sound system", "Borrowed room", "A scene"] })],
];

export const VisualCompositions: React.FC = () => (
  <>
    {TEMPLATES.map(([id, component, defaults]) => (
      <Composition
        key={id}
        id={id}
        component={component}
        durationInFrames={defaults.durationInFrames}
        fps={30}
        width={defaults.dimensions.width}
        height={defaults.dimensions.height}
        defaultProps={defaults}
        calculateMetadata={meta}
      />
    ))}
  </>
);
