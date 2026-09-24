/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: {
          base: "#070b14",
          surface: "#0f172a",
          elevated: "#111a2e",
        },
        border: {
          subtle: "rgba(148, 163, 184, 0.12)",
          active: "rgba(99, 102, 241, 0.4)",
        },
        brand: {
          DEFAULT: "#6366f1",
          hover: "#4f46e5",
          glow: "rgba(99, 102, 241, 0.35)",
        },
        node: {
          request: "#3b82f6",
          function: "#8b5cf6",
          crypto: "#f59e0b",
          storage: "#10b981",
          value: "#64748b",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 0 20px -5px rgba(99, 102, 241, 0.3)",
        "glow-green": "0 0 20px -5px rgba(34, 197, 94, 0.3)",
      },
    },
  },
  plugins: [],
}
