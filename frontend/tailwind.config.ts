import type { Config } from "tailwindcss";

// Black Volt Mobility brand palette — "Silent Power. Premium Arrival."
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        void: "#0A0A0F", // void black — base background
        obsidian: "#15151D", // obsidian gray — surfaces/cards
        volt: "#00E5FF", // electric cyan — primary accent
        "volt-dim": "#00B8CC",
        silver: "#C7CBD4", // cloud silver — muted text
        arctic: "#F5F7FA", // arctic white — bright text
      },
      fontFamily: {
        display: ["var(--font-rajdhani)", "system-ui", "sans-serif"],
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        volt: "0 0 24px rgba(0, 229, 255, 0.35)",
      },
    },
  },
  plugins: [],
};

export default config;
