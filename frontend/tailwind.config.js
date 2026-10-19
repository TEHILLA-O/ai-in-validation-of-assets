/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: "#17212b",
        navy: "#0d1b2a",
        paper: "#f4f1ea",
        card: "#fffcf7",
        line: "#d9d3c7",
        teal: "#0f6e6b",
        signal: "#8d3b32",
        input: "#e7f0fb",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
