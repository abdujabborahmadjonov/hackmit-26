/** The EduMatch mark: two figures shaking hands, forming an M under a
 *  graduation cap, inside a squircle. */

/** A superellipse, not a rounded rectangle.
 *
 *  `border-radius` gives you a square with circular corners, and the join
 *  where the arc meets the straight edge is visible at this size. A squircle
 *  curves continuously from corner to corner, which is why icons on phones
 *  use one. Drawn as a path so the stroke follows the real curve. */
const SQUIRCLE =
  "M50 2 C82 2 98 18 98 50 C98 82 82 98 50 98 C18 98 2 82 2 50 C2 18 18 2 50 2 Z";

export function Logo({
  size = 32,
  ring = true,
  className,
}: {
  size?: number;
  /** The squircle outline. Off where the mark sits on a busy surface. */
  ring?: boolean;
  className?: string;
}) {
  return (
    <span
      className={"relative inline-grid shrink-0 place-items-center " + (className ?? "")}
      style={{ width: size, height: size }}
    >
      {ring && (
        <svg
          viewBox="0 0 100 100"
          aria-hidden="true"
          className="absolute inset-0 h-full w-full text-indigo-600/25"
        >
          <path d={SQUIRCLE} fill="none" stroke="currentColor" strokeWidth="4" />
        </svg>
      )}
      <img
        src="/logo.png"
        alt=""
        loading="lazy"
        // Inset so the mark breathes inside the ring rather than touching it.
        className="object-contain"
        style={{ width: size * 0.68, height: size * 0.68 }}
      />
    </span>
  );
}

/** Mark plus name, which is how it appears in every header. */
export function Wordmark({
  size = 32,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={
        "flex shrink-0 items-center gap-2.5 font-semibold tracking-tight " + (className ?? "")
      }
    >
      <Logo size={size} />
      EduMatch
    </span>
  );
}
