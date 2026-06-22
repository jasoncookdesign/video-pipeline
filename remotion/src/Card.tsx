import React from "react";
import { AbsoluteFill, Img } from "remotion";
import type { CardProps } from "./types";
// Side-effect import: registers the loadable brand fonts so style.font_family
// renders in that typeface (shared with the caption composition).
import "./fonts";

// The source card (INI-089 Phase B). A deterministic, static tile: the component
// renders the card art filling its own composition frame (which equals the
// placement rect chosen in overlay.def). The on-screen *window* and the fade are
// applied downstream by the ffmpeg overlay primitive, so there is no per-frame
// animation here — the render is the same every frame, which keeps it cheap and
// predictable. Branding/polish iterate by editing CardStyle props, not the cut.

export const Card: React.FC<CardProps> = ({ style, content }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-start",
          gap: Math.round(style.padding * 0.4),
          backgroundColor: style.bg_color,
          borderRadius: style.corner_radius,
          padding: style.padding,
          fontFamily: style.font_family,
          color: style.text_color,
          boxSizing: "border-box",
          overflow: "hidden",
        }}
      >
        {content.image ? (
          <Img
            src={content.image}
            style={{
              width: "100%",
              maxHeight: "50%",
              objectFit: "cover",
              borderRadius: Math.round(style.corner_radius * 0.6),
            }}
          />
        ) : null}

        <div
          style={{
            fontSize: style.heading_size,
            fontWeight: 800,
            lineHeight: 1.1,
          }}
        >
          {content.heading}
        </div>

        {content.body ? (
          <div
            style={{
              fontSize: style.body_size,
              fontWeight: 400,
              lineHeight: 1.3,
              opacity: 0.92,
            }}
          >
            {content.body}
          </div>
        ) : null}

        <div
          style={{
            marginTop: "auto",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            fontSize: style.footer_size,
          }}
        >
          <span style={{ opacity: 0.7 }}>{content.footer}</span>
          {content.citation ? (
            <span style={{ color: style.accent_color, fontWeight: 700 }}>
              {content.citation}
            </span>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
