/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        amoled: {
          bg: "#050508",
          card: "#0d0f17",
          border: "#1b202e",
          hover: "#141824",
          input: "#090b12"
        },
        electric: {
          50: "#eff6ff",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          glow: "rgba(59, 130, 246, 0.15)"
        }
      }
    },
  },
  plugins: [],
}
