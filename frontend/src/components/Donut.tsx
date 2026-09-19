import { useState } from "react";

/** Inline-SVG donut.
 *
 *  Slice order is FIXED by the caller and never sorted by value: the palette is
 *  validated on ring-adjacent pairs (including the wrap from last slice back to
 *  first), so re-ordering would put unvalidated hues next to each other.
 *  A 2px surface-coloured stroke keeps neighbouring fills from touching.
 */
export interface DonutSegment {
  key: string;
  label: string;
  value: number;
  colour: string;
}

const SURFACE = "#ffffff";
const TRACK = "#e8e8ef";

function polar(cx: number, cy: number, radius: number, angle: number) {
  return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)] as const;
}

function arcPath(
  cx: number,
  cy: number,
  outer: number,
  inner: number,
  start: number,
  end: number,
): string {
  const large = end - start > Math.PI ? 1 : 0;
  const [ox1, oy1] = polar(cx, cy, outer, start);
  const [ox2, oy2] = polar(cx, cy, outer, end);
  const [ix2, iy2] = polar(cx, cy, inner, end);
  const [ix1, iy1] = polar(cx, cy, inner, start);
  return [
    `M ${ox1} ${oy1}`,
    `A ${outer} ${outer} 0 ${large} 1 ${ox2} ${oy2}`,
    `L ${ix2} ${iy2}`,
    `A ${inner} ${inner} 0 ${large} 0 ${ix1} ${iy1}`,
    "Z",
  ].join(" ");
}

interface DonutProps {
  segments: DonutSegment[];
  /** Denominator. Anything unclaimed renders as a neutral track. */
  total?: number;
  size?: number;
  thickness?: number;
  centreValue: string;
  centreCaption: string;
  /** Formats a segment's value for the hover state and the aria label. */
  format?: (value: number) => string;
}

export function Donut({
  segments,
  total = 1,
  size = 168,
  thickness = 26,
  centreValue,
  centreCaption,
  format = (value) => `${Math.round(value * 100)}%`,
}: DonutProps) {
  const [active, setActive] = useState<string | null>(null);
  const cx = size / 2;
  const cy = size / 2;
  const outer = size / 2 - 2;
  const inner = outer - thickness;

  const claimed = segments.reduce((sum, segment) => sum + Math.max(segment.value, 0), 0);
  const denominator = Math.max(total, claimed, 0.0001);

  let cursor = -Math.PI / 2;
  const arcs = segments.map((segment) => {
    const sweep = (Math.max(segment.value, 0) / denominator) * Math.PI * 2;
    const start = cursor;
    cursor += sweep;
    return { ...segment, start, end: cursor, sweep };
  });

  const hovered = arcs.find((arc) => arc.key === active) ?? null;
  const label = segments.map((s) => `${s.label} ${format(s.value)}`).join(", ");

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`${centreCaption} ${centreValue}. ${label}.`}
      onMouseLeave={() => setActive(null)}
    >
      {/* Unclaimed remainder: what a perfect match would still have earned. */}
      <circle cx={cx} cy={cy} r={(outer + inner) / 2} fill="none" stroke={TRACK} strokeWidth={thickness} />

      {arcs.map((arc) =>
        arc.sweep <= 0.0001 ? null : (
          <path
            key={arc.key}
            d={arcPath(cx, cy, outer, inner, arc.start, arc.end)}
            fill={arc.colour}
            stroke={SURFACE}
            strokeWidth={2}
            opacity={active && active !== arc.key ? 0.35 : 1}
            style={{ transition: "opacity 140ms ease-out" }}
            onMouseEnter={() => setActive(arc.key)}
          />
        ),
      )}

      {hovered ? (
        <>
          <text
            x={cx}
            y={cy - 4}
            textAnchor="middle"
            className="fill-ink"
            style={{ fontSize: size * 0.17, fontWeight: 600 }}
          >
            {format(hovered.value)}
          </text>
          <text
            x={cx}
            y={cy + 14}
            textAnchor="middle"
            className="fill-muted"
            style={{ fontSize: size * 0.075 }}
          >
            {hovered.label}
          </text>
        </>
      ) : (
        <>
          <text
            x={cx}
            y={cy - 2}
            textAnchor="middle"
            className="fill-ink"
            style={{ fontSize: size * 0.2, fontWeight: 600 }}
          >
            {centreValue}
          </text>
          <text
            x={cx}
            y={cy + 16}
            textAnchor="middle"
            className="fill-muted"
            style={{ fontSize: size * 0.075 }}
          >
            {centreCaption}
          </text>
        </>
      )}
    </svg>
  );
}
