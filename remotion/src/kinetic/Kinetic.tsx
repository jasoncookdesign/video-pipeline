// KineticText — one continuous, transparent overlay layer: a static title held in
// the top of the safe zone for the whole clip, and kinetic text beneath it that
// reveals word by word at reading pace. Nothing is drawn outside the safe box.
//
// How a line moves:
//   - each word has its own entrance, staggered across the reveal, with a short
//     pause between phrases (the line is never animated as one block);
//   - the whole line drifts sideways while it reveals, counterbalancing the words
//     that appear one after another, and slides on as it leaves;
//   - an accent word gets a follow-up move once it has arrived (whip, bloom, swell);
//   - words leave phrase by phrase, accelerating.
// Word motions: resolve (blur to sharp), rise, slide, mask (up from a baseline
// clip), gather (in from the sides), diminish (rise, then the line softens).
// DH signature easing for entrances; no bounce, spring, or overshoot.
import React from "react";
import { AbsoluteFill, Easing, Sequence, interpolate, interpolateColors, useCurrentFrame } from "remotion";
import { EASE } from "../visuals/kit";
import type { Box, VisualStyle } from "../visuals/types";
import type { KineticProps, TextBeat, WordColor, WordPlan } from "./types";
import "../fonts";

// Content is inset by the glow's reach so the shadow is never clipped; the whole
// layer is clipped to the safe box so no motion can ever draw outside it.
// Mirrors video_pipeline.kinetic.layout.
const PAD = 28;
const LINE_SHARE = { statement: 0.9, aside: 0.78, question: 0.9 } as const;
const BAR_GAP = 28; // title text to accent bar
const BAR_H = 8;
const SHADOW = "0 2px 22px rgba(0,0,0,0.6), 0 0 3px rgba(0,0,0,0.55)";

const DRIFT_EASE = Easing.bezier(0.05, 0.8, 0.15, 1); // steep deceleration
const LEAVE = Easing.in(Easing.quad); // exits accelerate

const JUSTIFY = { top: "flex-start", middle: "center", bottom: "flex-end" } as const;
const ITEMS = { left: "flex-start", center: "center", right: "flex-end" } as const;

/** 0 to 1 over `dur` frames from `from`, clamped; a zero-length span is a step. */
const prog = (frame: number, from: number, dur: number, easing: (t: number) => number = EASE): number =>
  dur <= 0
    ? frame >= from ? 1 : 0
    : interpolate(frame, [from, from + dur], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing,
      });

const colorOf = (c: WordColor, s: VisualStyle): string =>
  c === "accent" ? s.accent : c === "warm" ? s.warm : c === "dim" ? s.text_2 : s.text;

/** A box relative to the safe box's origin. */
const rel = (b: Box, sb: Box): Box => ({ x: b.x - sb.x, y: b.y - sb.y, width: b.width, height: b.height });

const fam = (s: VisualStyle, f: "display" | "body") => (f === "display" ? s.display_font : s.body_font);

const Title: React.FC<{ p: KineticProps }> = ({ p }) => {
  const s = p.style;
  const b = rel(p.titleBox, p.safeBox);
  const w = b.width - 2 * PAD;
  return (
    <div style={{ position: "absolute", left: b.x + PAD, top: b.y + PAD, width: w, height: b.height - PAD }}>
      <div
        style={{
          fontFamily: fam(s, "display"),
          fontWeight: 900,
          fontSize: p.titlePx,
          lineHeight: 1.0,
          letterSpacing: "-0.01em",
          color: s.text,
          textShadow: SHADOW,
          textAlign: "left",
        }}
      >
        {p.title.toUpperCase()}
      </div>
      <div style={{ marginTop: BAR_GAP, width: 132, height: BAR_H, background: s.accent }} />
    </div>
  );
};

const WordSpan: React.FC<{ w: WordPlan; i: number; motion: TextBeat["motion"]; s: VisualStyle }> = ({
  w,
  i,
  motion,
  s,
}) => {
  const frame = useCurrentFrame();
  const pIn = prog(frame, w.inFrom, w.inFrames);
  const pOut = w.outFrames > 0 ? prog(frame, w.outFrom, w.outFrames - 1, LEAVE) : 0; // 1 on the last frame
  const pT = w.treatFrames > 0 ? prog(frame, w.treatFrom, w.treatFrames) : 0;
  const dir = i % 2 === 0 ? -1 : 1;

  let tx = 0;
  let ty = 0;
  let blur = 0;
  let scale = 1;
  let opacity = pIn;
  let inner: React.CSSProperties | null = null;
  switch (motion) {
    case "slide":
      tx = (1 - pIn) * 40;
      break;
    case "rise":
      ty = (1 - pIn) * 28;
      break;
    case "diminish":
      ty = (1 - pIn) * 18;
      break;
    case "resolve":
      blur = (1 - pIn) * 14;
      scale = 1.05 - 0.05 * pIn;
      break;
    case "gather": {
      const reach = w.color !== "text" ? 200 : 90;
      tx = dir * (1 - pIn) * reach;
      blur = (1 - pIn) * 8;
      break;
    }
    case "mask":
      opacity = 1;
      inner = { transform: `translateY(${(1 - pIn) * 112}%)` };
      break;
  }

  // accent treatment, after the word has arrived
  let skew = 0;
  let color = colorOf(w.color, s);
  if (w.treatment === "whip") skew = -12 * pT;
  if (w.treatment === "swell") scale *= 1 + 0.1 * pT;
  if (w.treatment === "bloom") {
    const to = w.color === "text" ? s.accent : colorOf(w.color, s);
    color = interpolateColors(pT, [0, 1], [s.text, to]);
  }

  const lean = `scale(${scale}) skewX(${skew}deg)`;
  const style: React.CSSProperties = {
    display: "inline-block",
    fontFamily: fam(s, w.family),
    fontWeight: w.weight,
    fontStyle: w.italic ? "italic" : "normal",
    fontSize: `${w.scale}em`,
    color,
    textShadow: SHADOW,
    opacity: opacity * (1 - pOut),
    transformOrigin: "0 100%",
    transform: `translate(${tx}px, ${ty}px) ${lean}`,
    filter: blur > 0.05 ? `blur(${blur}px)` : undefined,
    whiteSpace: "nowrap",
  };
  if (inner) {
    // mask reveal: the word rises from below a clip edge at its baseline box; the
    // accent treatment (scale, skew) stays on the outer word so it still plays
    return (
      <span style={{ ...style, transform: lean, clipPath: "inset(-40px -40px 0px -40px)", verticalAlign: "bottom" }}>
        <span style={{ display: "inline-block", ...inner }}>{w.text}</span>
      </span>
    );
  }
  return <span style={style}>{w.text}</span>;
};

const BodyBeat: React.FC<{ p: KineticProps; beat: TextBeat }> = ({ p, beat }) => {
  const frame = useCurrentFrame();
  const b = rel(p.bodyBox, p.safeBox);
  const inner = b.width - 2 * PAD;
  const width = inner * LINE_SHARE[beat.role];
  const s = p.style;
  const display = beat.words.length ? beat.words[0].family : "display";
  const groups: number[][] = [];
  beat.words.forEach((_, i) => {
    if (i > 0 && beat.words[i - 1].keep) groups[groups.length - 1].push(i);
    else groups.push([i]);
  });

  const pDrift = prog(frame, 0, beat.revealFrames, DRIFT_EASE);
  const exitStart = beat.durationInFrames - beat.exitFrames;
  const pLeave = beat.exitFrames > 0 ? prog(frame, exitStart, beat.exitFrames - 1, LEAVE) : 0;
  const away = -Math.sign(beat.driftPx || 1) * Math.abs(beat.driftPx) * 0.6; // keeps moving the way it came
  let tx = (1 - pDrift) * beat.driftPx + pLeave * away;

  let scale = 1;
  let spacing = 0;
  let soften = 1;
  if (beat.motion === "diminish") {
    const q = prog(frame, beat.revealFrames, Math.max(1, exitStart - beat.revealFrames));
    scale = 1 - 0.12 * q;
    spacing = 0.04 * q;
    soften = 1 - 0.2 * q; // never below 0.8 while held: stays legible
  }

  return (
    <div
      style={{
        position: "absolute",
        left: b.x + PAD,
        top: b.y + PAD,
        width: inner,
        height: b.height - 2 * PAD,
        display: "flex",
        flexDirection: "column",
        justifyContent: JUSTIFY[beat.slot],
        alignItems: ITEMS[beat.align],
      }}
    >
      <div
        style={{
          width,
          fontFamily: fam(s, display),
          fontSize: beat.sizePx,
          lineHeight: 1.2,
          textAlign: beat.align,
          letterSpacing: `${spacing}em`,
          opacity: soften,
          transform: `translateX(${tx}px) scale(${scale})`,
          transformOrigin: beat.align === "right" ? "100% 50%" : beat.align === "left" ? "0 50%" : "50% 50%",
        }}
      >
        {groups.map((idxs, g) => (
          <React.Fragment key={g}>
            {/* words of one accent phrase never break across lines */}
            <span style={{ display: "inline-block", whiteSpace: "nowrap" }}>
              {idxs.map((i, k) => (
                <React.Fragment key={i}>
                  <WordSpan w={beat.words[i]} i={i} motion={beat.motion} s={s} />
                  {k < idxs.length - 1 ? "\u00A0" : null}
                </React.Fragment>
              ))}
            </span>
            {g < groups.length - 1 ? " " : null}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export const KineticText: React.FC<KineticProps> = (p) => (
  <AbsoluteFill style={{ backgroundColor: "transparent" }}>
    <div
      style={{
        position: "absolute",
        left: p.safeBox.x,
        top: p.safeBox.y,
        width: p.safeBox.width,
        height: p.safeBox.height,
        overflow: "hidden",
      }}
    >
      <Title p={p} />
      {p.beats.map((beat) =>
        beat.kind === "text" ? (
          <Sequence key={beat.id} from={beat.from} durationInFrames={beat.durationInFrames}>
            <BodyBeat p={p} beat={beat} />
          </Sequence>
        ) : null,
      )}
    </div>
  </AbsoluteFill>
);
