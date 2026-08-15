"use client";

import { useState } from "react";
import type { NotificationPreference } from "@/lib/types";
import { Panel } from "@/components/dashboard/Panel";

function PreferenceRow({ preference }: { preference: NotificationPreference }) {
  const [enabled, setEnabled] = useState(preference.enabled);
  const [saving, setSaving] = useState(false);

  async function toggle() {
    const next = !enabled;
    setEnabled(next); // optimistic
    setSaving(true);
    try {
      const res = await fetch(`/api/notification-preferences/${preference.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      if (!res.ok) throw new Error("save failed");
    } catch {
      setEnabled(!next); // revert on failure
    } finally {
      setSaving(false);
    }
  }

  return (
    <label className="flex items-center gap-4 py-4 text-sm text-cerebro-ink">
      <input
        type="checkbox"
        checked={enabled}
        disabled={saving}
        onChange={toggle}
        className="h-4 w-4 accent-cerebro-accent-light disabled:cursor-not-allowed"
      />
      {preference.label}
    </label>
  );
}

export function NotificationPreferencesPanel({
  preferences,
}: {
  preferences: NotificationPreference[];
}) {
  return (
    <Panel title="Notification preferences">
      <div className="divide-y divide-cerebro-border border-y border-cerebro-border">
        {preferences.map((pref) => (
          <PreferenceRow key={pref.id} preference={pref} />
        ))}
      </div>
    </Panel>
  );
}
