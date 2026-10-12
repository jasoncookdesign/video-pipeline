// The visual template library (#62). Each template mimics its target genre
// (game HUD, storefront, SaaS dashboard, installer, timeline, flowchart, title
// card) inside the shared DH frame, and is built to read in a second or two:
// one idea per panel, big type, everything settled by ~55% of the beat.
//
// Sizes come from the style's type scale (validated floors at the Python
// boundary); fitted text shrinks toward those floors, never below them.
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import {
  At,
  DhFrame,
  EASE,
  HAIR,
  fitText,
  formatNumber,
  monoLabel,
  staggerStep,
  useProgress,
  useReveal,
} from "./kit";
import type {
  Box,
  FlowchartProps,
  GameHudProps,
  ProgressBarProps,
  StatDashboardProps,
  StoreCardProps,
  TextCardProps,
  TimelineProps,
  VisualProps,
  VisualStyle,
} from "./types";

const display = (s: VisualStyle, px: number, weight = 900): React.CSSProperties => ({
  fontFamily: s.display_font,
  fontSize: px,
  fontWeight: weight,
  lineHeight: 0.98,
  letterSpacing: "-0.03em",
  textTransform: "uppercase",
  color: s.text,
});

const body = (s: VisualStyle, px?: number, weight = 600): React.CSSProperties => ({
  fontFamily: s.body_font,
  fontSize: Math.max(px ?? s.body_px, s.body_px),
  fontWeight: weight,
  lineHeight: 1.2,
  color: s.text,
});

const inset = (b: Box, top: number, right = top, bottom = top, left = right): Box => ({
  x: b.x + left,
  y: b.y + top,
  width: b.width - left - right,
  height: b.height - top - bottom,
});

// ── text-card ────────────────────────────────────────────────────────────────

export const TextCard: React.FC<VisualProps<TextCardProps>> = (v) => {
  const s = v.style;
  const p = v.props;
  const eyebrow = useReveal(2);
  const title = useReveal(5, 12, 36);
  const sub = useReveal(10);
  const src = useReveal(14);
  return (
    <DhFrame v={v}>
      {(c) => {
        const reserve =
          (p.eyebrow ? s.label_px * 2 : 0) +
          (p.subtitle ? s.body_px * 1.25 * 2 + 24 : 0) +
          (p.source ? s.label_px * 2 : 0);
        const big = v.layout === "full-graphic" ? s.title_px * 2.6 : s.title_px * 1.25;
        const tpx = fitText(p.title, c.width, c.height - reserve, big, v.minType.title_px);
        return (
          <At box={c} style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 24 }}>
            {p.eyebrow ? <div style={{ ...monoLabel(s, s.accent), ...eyebrow }}>[ {p.eyebrow} ]</div> : null}
            <div style={{ ...display(s, tpx), overflowWrap: "anywhere", ...title }}>{p.title}</div>
            {p.subtitle ? (
              <div style={{ ...body(s, s.body_px * 1.15, 600), color: s.text_2, ...sub }}>{p.subtitle}</div>
            ) : null}
            {p.source ? (
              <div style={{ ...monoLabel(s), marginTop: 12, ...src }}>{p.source}</div>
            ) : null}
          </At>
        );
      }}
    </DhFrame>
  );
};

// ── game-hud ─────────────────────────────────────────────────────────────────

const Padlock: React.FC<{ color: string; size: number }> = ({ color, size }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" style={{ flex: "none" }}>
    <path d="M7 11V8a5 5 0 0 1 10 0v3" fill="none" stroke={color} strokeWidth={2.6} />
    <rect x={4.5} y={11} width={15} height={11} fill={color} />
  </svg>
);

const Coin: React.FC<{ color: string; ink: string; size: number }> = ({ color, ink, size }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" style={{ flex: "none" }}>
    <circle cx={12} cy={12} r={11} fill={color} />
    <circle cx={12} cy={12} r={7.5} fill="none" stroke={ink} strokeWidth={2} />
  </svg>
);

export const GameHud: React.FC<VisualProps<GameHudProps>> = (v) => {
  const s = v.style;
  const p = v.props;
  const frame = useCurrentFrame();
  const items = p.stack?.items ?? [];
  const step = staggerStep(items.length + 2, v.beatFrames);
  const coinP = useProgress(4, Math.min(36, Math.round(v.beatFrames * 0.5)));
  const bar = useReveal(0, 8);
  const ach = useReveal(6 + step * items.length);
  const toast = useReveal(10 + step * (items.length + 1), 8, 40);
  const radius = 16; // game UI chrome is rounded — the mimic, not the DH frame
  return (
    <DhFrame v={v}>
      {(c) => {
        const barH = Math.round(s.heading_px * 1.5);
        const titlePx = fitText(p.title, c.width - 240, s.heading_px, s.heading_px, v.minType.body_px);
        const bodyBox = inset({ ...c, y: c.y + barH + 20, height: c.height - barH - 20 }, 0);
        const colGap = 24;
        const leftW = p.stack ? Math.round(bodyBox.width * 0.52) : 0;
        const rightW = bodyBox.width - leftW - (p.stack ? colGap : 0);
        const tileH = items.length
          ? Math.min(Math.round(s.body_px * 1.55), Math.floor((bodyBox.height - s.label_px * 2 - 8 * items.length) / items.length))
          : 0;
        return (
          <>
            {/* title bar */}
            <At
              box={{ ...c, height: barH }}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                background: s.surface_2,
                border: `${HAIR + 1}px solid ${s.line_2}`,
                borderRadius: radius,
                padding: "0 24px",
                ...bar,
              }}
            >
              <div style={{ ...display(s, titlePx, 900), letterSpacing: "0.01em", whiteSpace: "nowrap" }}>{p.title}</div>
              <div
                style={{
                  ...monoLabel(s, s.accent_ink),
                  background: s.accent,
                  borderRadius: 999,
                  padding: "6px 16px",
                }}
              >
                LVL 99
              </div>
            </At>
            {/* left: the stack that piles up */}
            {p.stack ? (
              <At box={{ ...bodyBox, width: leftW }} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ ...monoLabel(s), marginBottom: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.stack.label}</div>
                {items.map((it, i) => {
                  const start = 6 + i * step;
                  const pin = interpolate(frame, [start, start + 8], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                    easing: EASE,
                  });
                  const newest = frame >= start && (i === items.length - 1 || frame < 6 + (i + 1) * step);
                  const last = i === items.length - 1;
                  return (
                    <div
                      key={i}
                      style={{
                        height: tileH,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "0 20px",
                        borderRadius: radius * 0.6,
                        background: newest ? s.accent : s.surface,
                        border: `${HAIR}px solid ${newest ? s.accent : s.line_2}`,
                        opacity: pin,
                        transform: `translateX(${(1 - pin) * -60}px) scale(${0.9 + 0.1 * pin})`,
                        boxSizing: "border-box",
                      }}
                    >
                      <span style={{ ...display(s, s.body_px, 800), color: newest ? s.accent_ink : s.text, letterSpacing: "0.02em" }}>
                        {it}
                      </span>
                      <span style={{ ...monoLabel(s, newest ? s.accent_ink : s.text_2) }}>
                        {last ? "NEW" : `T${i + 1}`}
                      </span>
                    </div>
                  );
                })}
              </At>
            ) : null}
            {/* right: currency, achievement, toast */}
            <At
              box={{ ...bodyBox, x: bodyBox.x + leftW + (p.stack ? colGap : 0), width: rightW }}
              style={{ display: "flex", flexDirection: "column", gap: 20 }}
            >
              {p.currency ? (
                <div
                  style={{
                    background: s.surface,
                    border: `${HAIR}px solid ${s.line_2}`,
                    borderRadius: radius,
                    padding: "18px 20px",
                  }}
                >
                  <div style={{ ...monoLabel(s), marginBottom: 8 }}>{p.currency.label}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <Coin color={s.warm} ink={s.ground} size={s.heading_px} />
                    <span style={{ ...display(s, fitText(formatNumber(p.currency.value), rightW - s.heading_px - 60, s.heading_px * 1.2, s.heading_px * 1.1, v.minType.body_px, 0.66), 900), color: s.warm, whiteSpace: "nowrap" }}>
                      {formatNumber(Math.round(p.currency.value * coinP))}
                    </span>
                  </div>
                </div>
              ) : null}
              {p.achievement ? (
                <div
                  style={{
                    ...ach,
                    background: s.surface,
                    border: `${HAIR}px dashed ${p.achievement.state === "locked" ? s.line_2 : s.accent}`,
                    borderRadius: radius,
                    padding: "18px 20px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  <div style={{ ...monoLabel(s) }}>ACHIEVEMENT</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                    {p.achievement.state === "locked" ? <Padlock color={s.alert} size={s.heading_px * 0.9} /> : null}
                    <span
                      style={{
                        ...display(s, s.body_px * 1.1, 900),
                        color: p.achievement.state === "locked" ? s.text_2 : s.accent,
                      }}
                    >
                      {p.achievement.label}
                    </span>
                  </div>
                  <div style={{ ...monoLabel(s, p.achievement.state === "locked" ? s.alert : s.accent) }}>
                    {p.achievement.state === "locked" ? "LOCKED" : "UNLOCKED"}
                  </div>
                </div>
              ) : null}
              {p.toast ? (
                <div
                  style={{
                    ...toast,
                    ...display(s, fitText(p.toast, rightW - 36, s.body_px, s.body_px, v.minType.body_px), 800),
                    whiteSpace: "nowrap",
                    color: s.accent_ink,
                    background: s.warm,
                    borderRadius: radius * 0.6,
                    padding: "14px 18px",
                    letterSpacing: "0.01em",
                  }}
                >
                  {p.toast}
                </div>
              ) : null}
            </At>
          </>
        );
      }}
    </DhFrame>
  );
};

// ── store-card ───────────────────────────────────────────────────────────────

export const StoreCard: React.FC<VisualProps<StoreCardProps>> = (v) => {
  const s = v.style;
  const p = v.props;
  const feats = p.features ?? [];
  const step = staggerStep(feats.length + 3, v.beatFrames);
  const card = useReveal(0, 10, 30);
  const price = useReveal(step * 2, 8);
  const cta = useReveal(step * (feats.length + 3), 8);
  const frame = useCurrentFrame();
  const radius = 22; // storefront chrome
  return (
    <DhFrame v={v}>
      {(c) => {
        const pad = 32;
        const inner = inset(c, pad);
        const tpx = fitText(p.title, inner.width, s.heading_px * 1.1, s.heading_px * 1.1, v.minType.body_px);
        return (
          <At
            box={c}
            style={{
              background: s.surface,
              border: `${HAIR}px solid ${s.line_2}`,
              borderRadius: radius,
              padding: pad,
              display: "flex",
              flexDirection: "column",
              gap: 14,
              ...card,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              {p.eyebrow ? <div style={{ ...monoLabel(s, s.accent) }}>{p.eyebrow}</div> : <div />}
              {p.badge ? (
                <div style={{ ...monoLabel(s, s.accent_ink), background: s.warm, borderRadius: 999, padding: "6px 18px" }}>
                  {p.badge}
                </div>
              ) : null}
            </div>
            <div style={{ ...display(s, tpx, 900), whiteSpace: "nowrap" }}>{p.title}</div>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", columnGap: 18, ...price }}>
              <span style={{ ...display(s, s.heading_px * 1.3, 900), color: s.warm, letterSpacing: "-0.02em" }}>
                {p.price}
              </span>
              {p.price_note ? <span style={{ ...body(s, s.body_px, 500), color: s.text_2 }}>{p.price_note}</span> : null}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
              {feats.map((f, i) => {
                const start = step * (3 + i);
                const op = interpolate(frame, [start, start + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });
                return (
                  <div key={i} style={{ ...body(s, s.body_px, 600), display: "flex", gap: 14, opacity: op }}>
                    <span style={{ color: s.accent, fontWeight: 900 }}>✓</span>
                    <span>{f}</span>
                  </div>
                );
              })}
            </div>
            <div
              style={{
                marginTop: "auto",
                ...cta,
                ...display(s, s.body_px * 1.05, 900),
                letterSpacing: "0.06em",
                color: s.accent_ink,
                background: s.accent,
                borderRadius: radius * 0.6,
                textAlign: "center",
                padding: "18px 0",
              }}
            >
              {p.cta}
            </div>
          </At>
        );
      }}
    </DhFrame>
  );
};

// ── stat-dashboard ───────────────────────────────────────────────────────────

const Sparkline: React.FC<{ seed: number; color: string; width: number; height: number; progress: number }> = ({
  seed,
  color,
  width,
  height,
  progress,
}) => {
  // Deterministic up-and-to-the-right squiggle (no randomness across renders).
  const n = 12;
  const pts: string[] = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const wobble = Math.sin((i + 1) * (seed + 1.7) * 1.3) * 0.18;
    const y = 1 - Math.min(1, Math.max(0, t * 0.8 + 0.1 + wobble));
    pts.push(`${(t * width).toFixed(1)},${(y * height).toFixed(1)}`);
  }
  const len = width * 1.6;
  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <polyline
        points={pts.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={4}
        strokeLinejoin="round"
        strokeDasharray={len}
        strokeDashoffset={len * (1 - progress)}
      />
    </svg>
  );
};

export const StatDashboard: React.FC<VisualProps<StatDashboardProps>> = (v) => {
  const s = v.style;
  const p = v.props;
  const n = p.stats.length;
  const countDur = Math.min(40, Math.round(v.beatFrames * 0.55));
  const prog = useProgress(4, countDur);
  const head = useReveal(0, 8);
  const foot = useReveal(countDur, 8);
  const frame = useCurrentFrame();
  const radius = 12; // SaaS chrome
  return (
    <DhFrame v={v}>
      {(c) => {
        const headH = Math.round(s.heading_px * 1.1);
        const footH = p.footnote ? Math.round(s.label_px * 2.8) : 0;
        const grid: Box = { ...c, y: c.y + headH + 18, height: c.height - headH - 18 - footH };
        // tall boxes (full-graphic) stack tiles; wide panels use a 2-up grid
        const cols = n === 1 || grid.height >= grid.width ? 1 : 2;
        const rows = Math.ceil(n / cols);
        const gap = 18;
        const tileW = (grid.width - gap * (cols - 1)) / cols;
        const tileH = (grid.height - gap * (rows - 1)) / rows;
        return (
          <>
            <At box={{ ...c, height: headH }} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", ...head }}>
              <div style={{ ...display(s, fitText(p.title, c.width * 0.65, headH, s.heading_px, v.minType.body_px), 900) }}>
                {p.title}
              </div>
              <div style={{ ...monoLabel(s, s.text), display: "flex", alignItems: "center", gap: 10, border: `${HAIR}px solid ${s.line_2}`, borderRadius: radius, padding: "8px 14px" }}>
                <span style={{ width: 14, height: 14, borderRadius: 7, background: s.warm, opacity: 0.6 + 0.4 * Math.abs(Math.sin(frame / 8)) }} />
                LIVE
              </div>
            </At>
            {p.stats.map((st, i) => {
              const col = i % cols;
              const row = Math.floor(i / cols);
              const box: Box = { x: grid.x + col * (tileW + gap), y: grid.y + row * (tileH + gap), width: tileW, height: tileH };
              const from = st.from ?? 0;
              const val = from + (st.value - from) * prog;
              const txt = `${st.prefix ?? ""}${formatNumber(val, st.decimals ?? 0)}${st.suffix ?? ""}`;
              const finalTxt = `${st.prefix ?? ""}${formatNumber(st.value, st.decimals ?? 0)}${st.suffix ?? ""}`;
              const numPx = fitText(finalTxt, box.width - 48, box.height * 0.45, s.heading_px * (cols === 1 ? 2.2 : 1.6), v.minType.body_px, 0.66);
              const tileIn = interpolate(frame, [i * 3, i * 3 + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });
              return (
                <At
                  key={i}
                  box={box}
                  style={{
                    background: s.surface,
                    border: `${HAIR}px solid ${s.line_2}`,
                    borderRadius: radius,
                    padding: 24,
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    opacity: tileIn,
                  }}
                >
                  <div style={{ ...monoLabel(s), whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{st.label}</div>
                  <div style={{ ...display(s, numPx, 900), letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{txt}</div>
                  <Sparkline seed={i} color={s.accent} width={box.width - 48} height={Math.max(24, Math.round(box.height * 0.16))} progress={prog} />
                </At>
              );
            })}
            {p.footnote ? (
              <At box={{ ...c, y: c.y + c.height - footH + 10, height: footH }} style={{ ...monoLabel(s), ...foot }}>
                {p.footnote}
              </At>
            ) : null}
          </>
        );
      }}
    </DhFrame>
  );
};

// ── progress-bar ─────────────────────────────────────────────────────────────

export const ProgressBar: React.FC<VisualProps<ProgressBarProps>> = (v) => {
  const s = v.style;
  const p = v.props;
  const from = p.from_pct ?? 0;
  const fill = useProgress(6, Math.round(v.beatFrames * 0.6));
  const frame = useCurrentFrame();
  const pct = from + (p.to_pct - from) * fill;
  const label = useReveal(0, 8);
  const cap = useReveal(10, 8);
  const cursorOn = Math.floor(frame / 12) % 2 === 0;
  return (
    <DhFrame v={v}>
      {(c) => {
        const lpx = fitText(p.label, c.width, s.heading_px * 2.2, s.heading_px * 1.2, s.heading_px);
        const barH = Math.round(s.heading_px * 1.3);
        return (
          <At box={c} style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 26 }}>
            <div style={{ ...display(s, lpx, 900), ...label }}>{p.label}</div>
            <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
              <div
                style={{
                  flex: 1,
                  height: barH,
                  border: `${HAIR}px solid ${s.line_2}`,
                  background: s.surface,
                  padding: 6,
                  boxSizing: "border-box",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${pct}%`,
                    background: `repeating-linear-gradient(-45deg, ${s.accent} 0 22px, ${s.accent}CC 22px 44px)`,
                    backgroundPositionX: -frame * 2,
                  }}
                />
              </div>
              <div style={{ ...display(s, s.heading_px, 900), width: s.heading_px * 2.6, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {Math.round(pct)}%
              </div>
            </div>
            {p.status ? (
              <div style={{ ...monoLabel(s, s.text), ...cap }}>
                {p.status}
                <span style={{ opacity: cursorOn ? 1 : 0, color: s.accent }}> ▍</span>
              </div>
            ) : null}
            {p.caption ? <div style={{ ...body(s, s.body_px, 500), color: s.text_2, ...cap }}>{p.caption}</div> : null}
          </At>
        );
      }}
    </DhFrame>
  );
};

// ── timeline ─────────────────────────────────────────────────────────────────

export const Timeline: React.FC<VisualProps<TimelineProps>> = (v) => {
  const s = v.style;
  const p = v.props;
  const frame = useCurrentFrame();
  const n = p.items.length;
  const step = staggerStep(n + 1, v.beatFrames);
  const head = useReveal(0, 8);
  return (
    <DhFrame v={v}>
      {(c) => {
        const titleH = p.title ? Math.round(s.heading_px * 1.25) : 0;
        const list: Box = { ...c, y: c.y + titleH, height: c.height - titleH };
        const rowH = Math.floor(list.height / n);
        const dot = Math.round(s.label_px * 0.8);
        const railX = list.x + dot / 2;
        const whenW = Math.ceil(Math.max(0, ...p.items.map((it) => (it.when ?? "").length)) * s.label_px * 0.78);
        return (
          <>
            {p.title ? (
              <At box={{ ...c, height: titleH }} style={{ ...display(s, fitText(p.title, c.width, titleH, s.heading_px, v.minType.body_px), 900), ...head }}>
                {p.title}
              </At>
            ) : null}
            <div style={{ position: "absolute", left: railX - HAIR / 2, top: list.y + rowH / 2, width: HAIR, height: rowH * (n - 1), background: s.line_2 }} />
            {p.items.map((it, i) => {
              const start = step * (i + 1);
              const pin = interpolate(frame, [start, start + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });
              const hot = p.emphasis_last && i === n - 1;
              const row: Box = { x: list.x, y: list.y + i * rowH, width: list.width, height: rowH };
              return (
                <At key={i} box={row} style={{ display: "flex", alignItems: "center", gap: 28, opacity: pin, transform: `translateX(${(1 - pin) * 40}px)` }}>
                  <div style={{ width: dot, height: dot, flex: "none", background: hot ? s.accent : s.ground, border: `${HAIR}px solid ${hot ? s.accent : s.text_2}` }} />
                  {it.when ? <div style={{ ...monoLabel(s, hot ? s.accent : s.text_2), width: whenW, flex: "none", whiteSpace: "nowrap" }}>{it.when}</div> : null}
                  <div
                    style={{
                      ...body(s, s.body_px * (hot ? 1.1 : 1), hot ? 800 : 600),
                      color: hot ? s.accent_ink : s.text,
                      background: hot ? s.accent : "transparent",
                      padding: hot ? "8px 16px" : 0,
                    }}
                  >
                    {it.label}
                  </div>
                </At>
              );
            })}
          </>
        );
      }}
    </DhFrame>
  );
};

// ── flowchart ────────────────────────────────────────────────────────────────

export const Flowchart: React.FC<VisualProps<FlowchartProps>> = (v) => {
  const s = v.style;
  const p = v.props;
  const frame = useCurrentFrame();
  const n = p.steps.length;
  const step = staggerStep(n + 1, v.beatFrames);
  const head = useReveal(0, 8);
  return (
    <DhFrame v={v}>
      {(c) => {
        const titleH = p.title ? Math.round(s.heading_px * 1.25) : 0;
        const area: Box = { ...c, y: c.y + titleH, height: c.height - titleH };
        const tall = area.height > area.width;
        const arrowH = Math.round(s.body_px * (tall ? 1.6 : 1.1));
        const boxH = Math.min(Math.round(s.body_px * (tall ? 3.4 : 2.4)), Math.floor((area.height - arrowH * (n - 1)) / n));
        const used = boxH * n + arrowH * (n - 1);
        const top = area.y + (area.height - used) / 2;
        const boxW = Math.round(area.width * 0.78);
        const left = area.x + (area.width - boxW) / 2;
        return (
          <>
            {p.title ? (
              <At box={{ ...c, height: titleH }} style={{ ...display(s, fitText(p.title, c.width, titleH, s.heading_px, v.minType.body_px), 900), ...head }}>
                {p.title}
              </At>
            ) : null}
            {p.steps.map((label, i) => {
              const start = step * (i + 1);
              const pin = interpolate(frame, [start, start + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });
              const last = i === n - 1;
              const y = top + i * (boxH + arrowH);
              return (
                <React.Fragment key={i}>
                  {i > 0 ? (
                    <div
                      style={{
                        position: "absolute",
                        left: area.x,
                        width: area.width,
                        top: y - arrowH,
                        height: arrowH,
                        display: "flex",
                        justifyContent: "center",
                        alignItems: "center",
                        color: s.text_2,
                        fontFamily: s.mono_font,
                        fontSize: arrowH * 0.9,
                        fontWeight: 700,
                        opacity: pin,
                      }}
                    >
                      ↓
                    </div>
                  ) : null}
                  <At
                    box={{ x: left, y, width: boxW, height: boxH }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      border: `${HAIR}px solid ${last ? s.accent : s.line_2}`,
                      background: last ? s.accent : s.surface,
                      borderRadius: last ? 0 : boxH / 2, // process pills; the punchline lands square
                      opacity: pin,
                      transform: `scale(${0.92 + 0.08 * pin})`,
                    }}
                  >
                    <span style={{ ...display(s, Math.max(s.body_px, fitText(label, boxW - 80, s.body_px * (tall ? 1.6 : 1.25), s.body_px * (tall ? 1.6 : 1.25), s.body_px)), 900), color: last ? s.accent_ink : s.text, letterSpacing: "0.01em", whiteSpace: "nowrap" }}>
                      {label}
                    </span>
                  </At>
                </React.Fragment>
              );
            })}
          </>
        );
      }}
    </DhFrame>
  );
};
