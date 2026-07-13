import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  size = "default",
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  size?: "default" | "sm";
  className?: string;
}) {
  const compact = size === "sm";
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-2 py-8" : "gap-3 py-16",
        className
      )}
    >
      <div
        className={cn(
          "flex items-center justify-center rounded-full bg-gradient-to-br from-primary/10 to-accent/10",
          compact ? "h-9 w-9" : "h-14 w-14"
        )}
      >
        <Icon className={cn("text-primary/70", compact ? "h-4 w-4" : "h-6 w-6")} />
      </div>
      <div>
        <p className={cn("font-medium text-foreground", compact ? "text-xs" : "text-sm")}>
          {title}
        </p>
        {description && (
          <p className={cn("mt-1 text-muted-foreground", compact ? "text-xs" : "text-sm")}>
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  );
}
