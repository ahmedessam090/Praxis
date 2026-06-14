import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...p }: ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-xl)] border border-border bg-card shadow-sm",
        className,
      )}
      {...p}
    />
  );
}

export function CardHeader({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("px-5 pt-4 pb-2", className)} {...p} />;
}

export function CardTitle({ className, ...p }: ComponentProps<"h3">) {
  return <h3 className={cn("text-sm font-semibold tracking-tight", className)} {...p} />;
}

export function CardBody({ className, ...p }: ComponentProps<"div">) {
  return <div className={cn("px-5 pb-5", className)} {...p} />;
}

export function Button({ className, ...p }: ComponentProps<"button">) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm",
        "font-medium text-white transition hover:opacity-90 disabled:opacity-50",
        "disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...p}
    />
  );
}

export function GhostButton({ className, ...p }: ComponentProps<"button">) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg border border-border px-3 py-2",
        "text-sm font-medium transition hover:bg-surface focus:outline-none",
        "focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...p}
    />
  );
}

export function Input({ className, ...p }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-10 rounded-lg border border-border bg-surface px-3 text-sm outline-none",
        "placeholder:text-muted focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...p}
    />
  );
}

const TONE: Record<string, string> = {
  bull: "bg-bull/15 text-bull border-bull/30",
  bear: "bg-bear/15 text-bear border-bear/30",
  neutral: "bg-neutral/15 text-neutral border-neutral/30",
  muted: "bg-muted/10 text-muted border-border",
};

export function Badge({
  tone = "muted",
  className,
  children,
}: {
  tone?: keyof typeof TONE;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent",
        className,
      )}
    />
  );
}
