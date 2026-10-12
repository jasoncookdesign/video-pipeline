// Shared kit for the visual templates: the DH frame every template sits in, the
// motion helpers (one easing, entrance, staggered reveals, counters), and
// text fitting that never drops below the style's legibility floors.
//
// The frame is the constant across templates — ground fill bleeding to the clip
// edges, a mono header row (brand label left, PARODY tag right), a hairline rule,
// and a barcode motif up in the bleed. Templates only draw inside `content`.
import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import type { Box, VisualProps, VisualStyle } from "./types";
// Side-effect import: registers the bundled OFL brand fonts.
import "../fonts";

// DH signature easing: cubic-bezier(.2,.7,.2,1).
export const EASE = Easing.bezier(0.2, 0.7, 0.2, 1);
export const HAIR = 3; // 1.5px web hairline, doubled for video at phone scale

/** 0→1 progress over `dur` frames starting at `start`, eased. */
export const useProgress = (start: number, dur: number): number => {
  const frame = useCurrentFrame();
  return interpolate(frame, [start, start + Math.max(1, dur)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE,
  });
};

/** Fade + rise entrance style (the DH scroll reveal, compressed for video). */
export const useReveal = (start: number, dur = 10, rise = 24): React.CSSProperties => {
  const p = useProgress(start, dur);
  return { opacity: p, transform: `translateY(${(1 - p) * rise}px)` };
};

/**
 * Stagger step (frames) so `n` items finish revealing within ~55% of the beat,
 * at most 10 frames apart — everything readable in a second or two.
 */
export const staggerStep = (n: number, beatFrames: number): number =>
  Math.max(3, Math.min(10, Math.floor((beatFrames * 0.55) / Math.max(1, n))));

/** Number formatting for counters. */
export const formatNumber = (v: number, decimals = 0): string =>
  v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

/**
 * Largest font size in [minPx, maxPx] at which `text` wraps into `box` (greedy
 * word wrap with an average glyph width of `charW` em; the default is tuned
 * for heavy uppercase display type). Never below `minPx` —
 * the schema's length caps guarantee the floor fits.
 */
export const fitText = (
  text: string,
  width: number,
  height: number,
  maxPx: number,
  minPx: number,
  charW = 0.74, // Archivo 900 uppercase averages ~0.7em; err wide so nothing overflows
  lineH = 1.0,
): number => {
  const words = text.split(/\s+/).filter(Boolean);
  for (let px = Math.floor(maxPx); px > minPx; px -= 2) {
    const perLine = Math.max(1, Math.floor(width / (px * charW)));
    if (words.some((w) => w.length > perLine)) continue;
    let lines = 1;
    let cur = 0;
    for (const w of words) {
      const need = cur === 0 ? w.length : cur + 1 + w.length;
      if (need > perLine) {
        lines += 1;
        cur = w.length;
      } else {
        cur = need;
      }
    }
    if (lines * px * lineH <= height) return px;
  }
  return minPx;
};

export const monoLabel = (s: VisualStyle, color?: string): React.CSSProperties => ({
  fontFamily: s.mono_font,
  fontSize: s.label_px,
  fontWeight: 700,
  letterSpacing: "0.14em",
  textTransform: "uppercase",
  color: color ?? s.text_2,
  lineHeight: 1.1,
});

/** The PARODY tag: boxed mono micro-label, accent, zero radius. */
export const ParodyTag: React.FC<{ s: VisualStyle }> = ({ s }) => (
  <div
    style={{
      ...monoLabel(s, s.accent_ink),
      background: s.accent,
      padding: `${Math.round(s.label_px * 0.28)}px ${Math.round(s.label_px * 0.5)}px`,
      whiteSpace: "nowrap",
    }}
  >
    {s.parody_label}
  </div>
);

const Barcode: React.FC<{ s: VisualStyle; width: number; height: number }> = ({ s, width, height }) => (
  <div
    style={{
      width,
      height,
      background: `repeating-linear-gradient(90deg, ${s.line_2} 0 3px, transparent 3px 7px, ${s.line_2} 7px 8px, transparent 8px 14px, ${s.line_2} 14px 19px, transparent 19px 23px)`,
      opacity: 0.8,
    }}
  />
);

export type FrameRender = (content: Box) => React.ReactNode;

/**
 * The DH frame. Fills the clip with the ground color, draws the header row and
 * rules inside the safe box, and hands the remaining content rect (absolute px
 * within the clip) to the template.
 */
export const DhFrame: React.FC<{ v: VisualProps<unknown>; children: FrameRender }> = ({ v, children }) => {
  const s = v.style;
  const sb = v.safeBox;
  const header = Math.round(s.label_px * 1.9);
  const gap = Math.round(s.label_px * 0.8);
  const enter = useReveal(0, 8, 0);
  const content: Box = {
    x: sb.x,
    y: sb.y + header + gap,
    width: sb.width,
    height: sb.height - header - gap * 2,
  };
  return (
    <AbsoluteFill style={{ backgroundColor: s.ground, overflow: "hidden" }}>
      {/* barcode motif up in the bleed above the safe box (decorative only) */}
      {sb.y >= 120 ? (
        <div style={{ position: "absolute", left: sb.x, top: sb.y - 96 }}>
          <Barcode s={s} width={Math.round(sb.width * 0.42)} height={44} />
        </div>
      ) : null}
      {/* header row: brand label | PARODY tag, on a hairline */}
      <div
        style={{
          position: "absolute",
          left: sb.x,
          top: sb.y,
          width: sb.width,
          height: header,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: `${HAIR}px solid ${s.line}`,
          boxSizing: "border-box",
          paddingBottom: Math.round(s.label_px * 0.35),
          ...enter,
        }}
      >
        <div style={{ ...monoLabel(s), display: "flex", gap: 14, alignItems: "center" }}>
          {s.brand_label ? (
            <>
              <span style={{ color: s.accent }}>◆</span>
              <span>{s.brand_label}</span>
            </>
          ) : null}
        </div>
        {v.parody ? <ParodyTag s={s} /> : null}
      </div>
      {children(content)}
      {/* accent seam where the panel meets the presenter (split layout) */}
      {v.layout === "split" ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            height: HAIR * 2,
            background: s.accent,
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};

/** Absolutely positioned content box helper. */
export const At: React.FC<{ box: Box; style?: React.CSSProperties; children?: React.ReactNode }> = ({
  box,
  style,
  children,
}) => (
  <div
    style={{
      position: "absolute",
      left: box.x,
      top: box.y,
      width: box.width,
      height: box.height,
      boxSizing: "border-box",
      ...style,
    }}
  >
    {children}
  </div>
);
