export const SCALES = [
  { id: "units", divisor: 1, label: "units" },
  { id: "thousands", divisor: 1_000, label: "thousands" },
  { id: "millions", divisor: 1_000_000, label: "millions" },
  { id: "billions", divisor: 1_000_000_000, label: "billions" },
] as const;

export type ScaleId = (typeof SCALES)[number]["id"];

function shiftPoint(unsigned: string, places: number): string {
  const [whole, fraction = ""] = unsigned.split(".");
  const digits = `${whole}${fraction}`;
  const point = whole.length + places;
  if (point <= 0) return `0.${"0".repeat(-point)}${digits}`;
  if (point >= digits.length) return `${digits}${"0".repeat(point - digits.length)}`;
  return `${digits.slice(0, point)}.${digits.slice(point)}`;
}

function roundHalfAway(unsigned: string, places: number): string {
  const shifted = unsigned;
  const [whole, fraction = ""] = shifted.split(".");
  const probe = (fraction + "0".repeat(places + 1)).slice(0, places + 1);
  let kept = probe.slice(0, places);
  if (probe[places] < "5") return trimWhole(`${whole || "0"}${places ? "." + kept : ""}`);
  const chars = `${whole}${kept}`.split("");
  let index = chars.length - 1;
  while (index >= 0 && chars[index] === "9") {
    chars[index] = "0";
    index -= 1;
  }
  if (index < 0) chars.unshift("1");
  else chars[index] = String(Number(chars[index]) + 1);
  const joined = chars.join("");
  const splitAt = joined.length - places;
  const nextWhole = splitAt <= 0 ? "0" : joined.slice(0, splitAt);
  const nextFraction = places ? joined.slice(splitAt).padStart(places, "0") : "";
  return trimWhole(places ? `${nextWhole}.${nextFraction}` : nextWhole);
}

function trimWhole(value: string): string {
  const [whole, fraction] = value.split(".");
  const trimmed = whole.replace(/^0+(?=\d)/, "") || "0";
  return fraction == null ? trimmed : `${trimmed}.${fraction}`;
}

function group(value: string, places: number, negative: boolean): string {
  const [whole, fraction = ""] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const body = places > 0 ? `${grouped}.${fraction.padEnd(places, "0").slice(0, places)}` : grouped;
  if (whole === "0" && (fraction === "" || /^0+$/.test(fraction))) {
    return places > 0 ? `0.${"0".repeat(places)}` : "0";
  }
  return negative ? `(${body})` : body;
}

export function formatMoney(raw: string | null | undefined, divisor: number, places = 2): string {
  if (raw == null || raw === "") return "—";
  const trimmed = raw.trim();
  const negative = trimmed.startsWith("-");
  const unsigned = negative ? trimmed.slice(1) : trimmed;
  if (!/^\d+(\.\d+)?$/.test(unsigned)) return raw;
  const shift = -(String(Math.round(divisor)).length - 1);
  const rounded = roundHalfAway(shiftPoint(unsigned, shift), places);
  return group(rounded, places, negative);
}

export function formatPercent(raw: string | null | undefined, places = 2): string {
  if (raw == null || raw === "") return "—";
  const trimmed = raw.trim();
  const negative = trimmed.startsWith("-");
  const unsigned = negative ? trimmed.slice(1) : trimmed;
  if (!/^\d+(\.\d+)?$/.test(unsigned)) return raw;
  const rounded = roundHalfAway(shiftPoint(unsigned, 2), places);
  const shown = group(rounded, places, negative);
  return `${shown}%`;
}

export function chartNumber(raw: string | null | undefined, divisor: number): number | null {
  if (raw == null || raw === "") return null;
  const value = Number(raw) / divisor;
  return Number.isFinite(value) ? value : null;
}
