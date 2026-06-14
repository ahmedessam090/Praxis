"use client";

import { Activity, CandlestickChart, LineChart } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LlmUsageBadge } from "@/components/llm-usage";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Market Regime", icon: Activity },
  { href: "/ticker", label: "Ticker Analysis", icon: CandlestickChart },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-surface/60 px-3 py-5 md:flex">
        <div className="flex items-center gap-2 px-2 pb-6">
          <LineChart className="text-brand" size={20} />
          <span className="text-sm font-semibold tracking-tight">TA Assistant</span>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                  active
                    ? "bg-brand/12 text-brand"
                    : "text-muted hover:bg-card hover:text-foreground",
                )}
              >
                <Icon size={16} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto px-2 text-[11px] leading-relaxed text-muted">
          Long-side classical TA. Decision support, not financial advice.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-border bg-background/80 px-5 backdrop-blur">
          <div className="flex items-center gap-2 text-sm text-muted md:hidden">
            <LineChart className="text-brand" size={18} />
            <span className="font-semibold text-foreground">TA Assistant</span>
          </div>
          <div className="hidden text-xs text-muted md:block">
            Classical market analysis · Temporal-durable
          </div>
          <div className="flex items-center gap-3">
            <LlmUsageBadge />
            <ThemeToggle />
          </div>
        </header>
        <main className="min-w-0 flex-1 px-5 py-6">{children}</main>
      </div>
    </div>
  );
}
