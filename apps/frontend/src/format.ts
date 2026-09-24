export const fmt = (value: number | undefined | null, suffix = "") =>
  value == null
    ? "—"
    : `${Number.isInteger(value) ? value : value.toFixed(1)}${suffix}`;
