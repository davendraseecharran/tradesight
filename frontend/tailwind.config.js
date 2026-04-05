/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0f1923',
          secondary: '#131c29',
          card: '#1a2535',
          hover: '#1e2d40',
          border: '#253248',
        },
        brand: '#2962ff',
        long: '#26a69a',
        short: '#ef5350',
        warn: '#f59e0b',
        muted: '#64748b',
        text: {
          primary: '#e2e8f0',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
