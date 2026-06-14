"use client";

import {
  Activity,
  CandlestickChart,
  LineChart,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { LlmUsageBadge } from "@/components/llm-usage";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Market Regime", icon: Activity },
  { href: "/screener", label: "Stock Screener", icon: Radar },
  { href: "/ticker", label: "Ticker Analysis", icon: CandlestickChart },
];

const STORAGE_KEY = "sidebar-collapsed";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY) === "1") setCollapsed(true);
  }, []);

  const toggle = () =>
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });

  return (
    <div className="flex min-h-screen">
      <aside
        className={cn(
          "hidden shrink-0 flex-col border-r border-border bg-surface/60 py-5 transition-[width] duration-200 md:flex",
          collapsed ? "w-16 px-2" : "w-60 px-3",
        )}
      >
        <div
          className={cn(
            "flex items-center pb-6",
            collapsed ? "justify-center" : "gap-2 px-2",
          )}
        >
          <LineChart className="shrink-0 text-brand" size={20} />
          {!collapsed && (
            <span className="text-sm font-semibold tracking-tight">TA Assistant</span>
          )}
        </div>

        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                title={collapsed ? label : undefined}
                className={cn(
                  "flex items-center rounded-lg py-2 text-sm font-medium transition",
                  collapsed ? "justify-center px-0" : "gap-3 px-3",
                  active
                    ? "bg-brand/12 text-brand"
                    : "text-muted hover:bg-card hover:text-foreground",
                )}
              >
                <Icon size={16} className="shrink-0" />
                {!collapsed && label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto flex flex-col gap-3">
          <button
            type="button"
            onClick={toggle}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "flex items-center rounded-lg py-2 text-xs font-medium text-muted transition hover:bg-card hover:text-foreground",
              collapsed ? "justify-center px-0" : "gap-2 px-3",
            )}
          >
            {collapsed ? (
              <PanelLeftOpen size={16} className="shrink-0" />
            ) : (
              <>
                <PanelLeftClose size={16} className="shrink-0" />
                Collapse
              </>
            )}
          </button>
          {!collapsed && (
            <div className="px-2 text-[11px] leading-relaxed text-muted">
              Long-side classical TA. Decision support, not financial advice.
            </div>
          )}
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
