import { humanize } from "../api/vocab";
import { cx } from "./ui";

/** Multi-select as toggleable chips - faster to scan than a multi <select>. */
export function ChipSelect({
  options,
  value,
  onChange,
  max,
}: {
  options: readonly string[];
  value: string[];
  onChange: (next: string[]) => void;
  max?: number;
}) {
  function toggle(option: string) {
    if (value.includes(option)) onChange(value.filter((v) => v !== option));
    else if (!max || value.length < max) onChange([...value, option]);
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const selected = value.includes(option);
        return (
          <button
            key={option}
            type="button"
            onClick={() => toggle(option)}
            aria-pressed={selected}
            className={cx(
              "rounded-full px-3 py-1 text-sm transition ring-1",
              selected
                ? "bg-indigo-600 text-white ring-indigo-600"
                : "bg-white text-muted ring-line hover:text-ink hover:ring-slate-300",
            )}
          >
            {humanize(option)}
          </button>
        );
      })}
    </div>
  );
}

/** Free-text terms (subjects, expertise) entered comma-separated. */
export function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <input
        className="w-full rounded-lg bg-white px-3 py-2 text-sm text-ink ring-1 ring-line placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        defaultValue={value.join(", ")}
        placeholder={placeholder}
        onBlur={(event) =>
          onChange(
            event.target.value
              .split(",")
              .map((part) => part.trim())
              .filter(Boolean),
          )
        }
      />
      {value.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {value.map((term) => (
            <span
              key={term}
              className="rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700"
            >
              {humanize(term)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
