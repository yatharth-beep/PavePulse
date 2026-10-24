/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          950: "#070b12",
          900: "#0c1320",
          800: "#121b2c",
          700: "#1a2740",
        },
      },
      boxShadow: {
        glow: "0 0 40px rgba(34, 211, 238, 0.12)",
      },
    },
  },
  plugins: [],
};
