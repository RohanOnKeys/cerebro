"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ApiKeyStatus, ChannelConfig, ChannelName } from "@/lib/types";

const CHANNEL_LABEL: Record<ChannelName, string> = {
  telegram: "Telegram",
  discord: "Discord",
  slack: "Slack",
  email: "Email",
};

const STATUS_LABEL: Record<ApiKeyStatus, string> = {
  configured: "Configured",
  missing: "Missing",
};

const STATUS_COLOR: Record<ApiKeyStatus, string> = {
  configured: "text-cerebro-success",
  missing: "text-cerebro-danger",
};

export function ChannelConfigRow({ config }: { config: ChannelConfig }) {
  const router = useRouter();
  const [status, setStatus] = useState(config.apiKeyStatus);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reconnect() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/channel-config/${config.channel}/reconnect`, {
        method: "POST",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? "reconnect failed");
      }
      const data = (await res.json()) as { apiKeyStatus: ApiKeyStatus };
      setStatus(data.apiKeyStatus);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "reconnect failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 items-center gap-3 py-5 sm:grid-cols-[220px_1fr_auto] sm:gap-4">
      <span className="text-base font-medium text-cerebro-ink">
        {CHANNEL_LABEL[config.channel]}
      </span>
      <span className={`text-sm ${STATUS_COLOR[status]}`}>
        API key: {STATUS_LABEL[status]}
        {error && <span className="ml-3 text-cerebro-danger">{error}</span>}
      </span>
      <button
        type="button"
        disabled={loading}
        onClick={reconnect}
        className="w-fit border border-cerebro-border px-4 py-2 text-xs font-medium text-cerebro-accent-lightest transition-colors hover:border-cerebro-accent-light disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Checking…" : "Reconnect"}
      </button>
    </div>
  );
}
