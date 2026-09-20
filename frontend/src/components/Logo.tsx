/** The EduMatch mark: two figures shaking hands, forming an M under a
 *  graduation cap. Served from /logo.png so it is one asset everywhere. */
export function Logo({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <img
      src="/logo.png"
      alt=""
      width={size}
      height={size}
      // The mark is taller than it is wide; `contain` keeps it from stretching
      // into whatever square the layout hands it.
      className={"shrink-0 object-contain " + (className ?? "")}
      style={{ width: size, height: size }}
    />
  );
}

/** Mark plus name, which is how it appears in every header. */
export function Wordmark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <span className={"flex shrink-0 items-center gap-2.5 font-semibold tracking-tight " + (className ?? "")}>
      <Logo size={size} />
      EduMatch
    </span>
  );
}
