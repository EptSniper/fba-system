import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        panel: "var(--panel)",
        panel2: "var(--panel-2)",
        side: "var(--side-bg)",
        line: "var(--border)",
        line2: "var(--border-strong)",
        ink: "var(--text)",
        muted: "var(--text-muted)",
        faint: "var(--text-faint)",
        accent: "var(--accent)",
        accent2: "var(--accent-2)",
        profit: "var(--profit)",
        loss: "var(--loss)",
        warn: "var(--warn)",
        info: "var(--info)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
    },
    // Operator-console aesthetic: flat, sharp rectangles everywhere (hairline borders do the
    // work shadows/rounding used to) — full override, not an extend, so every rounded-* utility
    // resolves flat. rounded-full stays circular for LED dots / avatar chips.
    borderRadius: {
      none: "0px",
      sm: "0px",
      DEFAULT: "0px",
      md: "0px",
      lg: "0px",
      xl: "0px",
      "2xl": "0px",
      "3xl": "0px",
      full: "9999px",
    },
  },
  plugins: [tailwindcssAnimate],
};

export default config;
