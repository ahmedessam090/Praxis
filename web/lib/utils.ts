import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Bias / status -> semantic color token name (used with text-/bg-/border- utilities). */
export type Status = "bullish" | "neutral" | "bearish";

export function statusColor(status: string): "bull" | "neutral" | "bear" {
  if (status === "bullish") return "bull";
  if (status === "bearish") return "bear";
  return "neutral";
}

export function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtSigned(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const s = fmt(Math.abs(value), digits);
  return `${value >= 0 ? "+" : "−"}${s}`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** ISO timestamp -> UNIX seconds (lightweight-charts native time). */
export function toUnix(ts: string): number {
  return Math.floor(new Date(ts).getTime() / 1000);
}
