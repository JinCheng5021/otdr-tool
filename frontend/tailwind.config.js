/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        "surface-tint": "#3350d5",
        "primary-fixed": "#dee1ff",
        "secondary-fixed-dim": "#c6c6c6",
        "on-primary-fixed": "#001159",
        "surface-container-lowest": "#ffffff",
        "secondary-container": "#e2e2e2",
        "error": "#ba1a1a",
        "secondary-fixed": "#e2e2e2",
        "on-tertiary-container": "#ff8f77",
        "on-secondary-container": "#646464",
        "background": "#fbf8ff",
        "on-surface": "#1a1b23",
        "primary": "#001e81",
        "error-container": "#ffdad6",
        "primary-container": "#002eb8",
        "on-error": "#ffffff",
        "tertiary-fixed-dim": "#ffb4a4",
        "on-primary-container": "#99a9ff",
        "surface-bright": "#fbf8ff",
        "secondary": "#5e5e5e",
        "on-secondary-fixed-variant": "#474747",
        "surface-container": "#eeedf8",
        "surface": "#fbf8ff",
        "inverse-on-surface": "#f1effb",
        "on-tertiary-fixed": "#3d0600",
        "tertiary": "#5b0c00",
        "tertiary-fixed": "#ffdad3",
        "surface-container-low": "#f4f2fe",
        "outline-variant": "#c5c5d7",
        "outline": "#757686",
        "tertiary-container": "#831600",
        "on-error-container": "#93000a",
        "surface-variant": "#e2e1ed",
        "primary-fixed-dim": "#b9c3ff",
        "on-tertiary": "#ffffff",
        "surface-container-highest": "#e2e1ed",
        "on-background": "#1a1b23",
        "on-surface-variant": "#444654",
        "inverse-surface": "#2f3038",
        "on-primary-fixed-variant": "#0e34bd",
        "on-secondary": "#ffffff",
        "inverse-primary": "#b9c3ff",
        "surface-dim": "#dad9e4",
        "on-primary": "#ffffff",
        "on-tertiary-fixed-variant": "#8a1c03",
        "surface-container-high": "#e8e7f2",
        "on-secondary-fixed": "#1b1b1b",
        "industrial-navy": "#001e81",
        "industrial-gray": "#444654",
        "status-pass": "#22c55e",
        "status-warning": "#f59e0b",
        "status-fail": "#ef4444"
      },
      borderRadius: {
        "DEFAULT": "0.125rem",
        "lg": "0.25rem",
        "xl": "0.5rem",
        "full": "0.75rem"
      },
      spacing: {
        "margin-mobile": "16px",
        "touch-target": "48px",
        "margin-desktop": "40px",
        "gutter": "24px",
        "unit": "8px"
      },
      fontFamily: {
        "body-lg": ["Inter", "sans-serif"],
        "mono-data": ["JetBrains Mono", "monospace"],
        "label-md": ["Inter", "sans-serif"],
        "headline-lg": ["Inter", "sans-serif"],
        "body-md": ["Inter", "sans-serif"],
        "headline-xl": ["Inter", "sans-serif"],
        "headline-md": ["Inter", "sans-serif"],
        "label-lg": ["Inter", "sans-serif"]
      },
      animation: {
        "shimmer": "shimmer 2s infinite linear",
        "pulse-soft": "pulse-soft 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-up": "fade-up 0.5s ease-out forwards"
      },
      keyframes: {
        "shimmer": {
          "0%": { "backgroundPosition": "-200% 0" },
          "100%": { "backgroundPosition": "200% 0" }
        },
        "pulse-soft": {
          "0%, 100%": { "opacity": "1" },
          "50%": { "opacity": "0.6" }
        },
        "fade-up": {
          "0%": { "opacity": "0", "transform": "translateY(20px)" },
          "100%": { "opacity": "1", "transform": "translateY(0)" }
        }
      }
    },
  },
  plugins: [],
}
