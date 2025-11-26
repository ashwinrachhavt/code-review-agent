import * as React from "react";
import { cn } from "@/lib/utils";

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number;
}

export function Progress({ value = 0, className, ...props }: ProgressProps) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-2 w-full overflow-hidden rounded bg-zinc-200 dark:bg-zinc-800", className)}
      {...props}
    >
      <div
        className="h-2 bg-zinc-900 transition-all dark:bg-zinc-600"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

