"use client";

import { ExternalLink, Gauge } from "lucide-react";
import { useLlmUsage } from "@/lib/api";

export function LlmUsageBadge() {
  const { data } = useLlmUsage();
  if (!data) return null;

  if (!data.enabled) {
    return (
      <span
        className="hidden items-center gap-1.5 text-xs text-muted sm:inline-flex"
        title="Set LANGFUSE_PUBLIC_KEY/SECRET_KEY in .env and `make langfuse-up`"
      >
        <Gauge size={14} /> LLM obs off
      </span>
    );
  }
  return (
    <a
      href={data.ui_url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted transition hover:bg-surface hover:text-foreground"
      title="Open Langfuse — LLM usage & cost"
    >
      <Gauge size={14} className="text-bull" />
      <span className="hidden sm:inline">
        {data.provider}
        {data.model ? ` · ${data.model}` : ""}
      </span>
      <span>Langfuse</span>
      <ExternalLink size={12} />
    </a>
  );
}
