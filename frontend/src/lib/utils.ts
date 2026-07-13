import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31536000],
  ["month", 2592000],
  ["week", 604800],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

const relativeFormatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function formatRelativeTime(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 45) return "just now";
  for (const [unit, secondsInUnit] of RELATIVE_UNITS) {
    if (seconds >= secondsInUnit) {
      return relativeFormatter.format(-Math.round(seconds / secondsInUnit), unit);
    }
  }
  return relativeFormatter.format(-Math.round(seconds / 60), "minute");
}
