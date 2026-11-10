import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0a0a0a",
        panel: "#efece6",
        line: "#ebe9e3",
        accent: "#3857d1",
        teal: {
          50: "#f1f3ff",
          100: "#e5e9ff",
          200: "#cbd4ff",
          300: "#a9b9ff",
          400: "#8197ff",
          500: "#5073ff",
          600: "#3857d1",
          700: "#304ab3",
          800: "#293d91",
          900: "#26377a",
          950: "#17204b"
        },
        slate: {
          50: "#fbfaf6",
          100: "#efece6",
          200: "#e6e3dc",
          300: "#d9d6cd",
          400: "#8b867d",
          500: "#6d6962",
          600: "#5f5d57",
          700: "#46423c",
          800: "#2a2620",
          900: "#1d1b18",
          950: "#141310"
        },
        warn: "#b45309"
      }
    }
  },
  plugins: []
};

export default config;
