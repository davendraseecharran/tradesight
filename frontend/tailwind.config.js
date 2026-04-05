/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0a',
          secondary: '#111111',
          card: '#161616',
          hover: '#1c1c1c',
          border: '#262626',
        },
        brand: '#ffffff',
        long: '#22c55e',
        short: '#ef4444',
        warn: '#eab308',
        muted: '#525252',
        text: {
          primary: '#fafafa',
          secondary: '#a3a3a3',
          muted: '#525252',
        },
      },
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
