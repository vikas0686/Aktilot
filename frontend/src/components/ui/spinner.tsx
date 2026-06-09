import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-spin rounded-full border-2 border-muted border-t-foreground", className)}
      role="status"
      aria-label="Loading"
    />
  );
}
