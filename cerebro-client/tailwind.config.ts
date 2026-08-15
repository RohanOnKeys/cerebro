import type { Config } from "tailwindcss";

// Design tokens taken directly from the approved Cerebro visual spec.
// Keep this file as the single source of truth for color/type — components
// should reference these tokens (bg-cerebro-bg, text-cerebro-accent, etc.)
// rather than hardcoding hex values, so a future rebrand is a one-file change.
//
// This is the client (marketing/landing) app's copy of the token set. The
// team dashboard app (cerebro-web) has its own copy plus a few
// dashboard-only additions (status colors, the Archivo display font) that
// don't belong here since this site has no status/table UI at all.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cerebro: {
          bg: "#1c1e22",
          "bg-raised": "#232629",
          border: "#33373d",
          accent: "#20568c",
          "accent-light": "#3d7ab5",
          "accent-lighter": "#6b93b0",
          "accent-lightest": "#a8bfd1",
          ink: "#e7e9ec",
          muted: "#9a9fa6",
        },
      },
      fontFamily: {
        // Unica One: this site's display face (hero, capability titles).
        landing: ["var(--font-unica)", "system-ui", "sans-serif"],
        // Work Sans: humanist, used for all body copy and labels.
        sans: ["var(--font-work-sans)", "system-ui", "sans-serif"],
      },
      maxWidth: {
        "8xl": "1920px",
      },
    },
  },
  plugins: [],
};

export default config;
