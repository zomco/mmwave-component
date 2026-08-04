/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#effcf6', 100: '#d8f8e9', 200: '#b4efd5', 300: '#7fe0b9',
          400: '#45c99a', 500: '#1daf7f', 600: '#0b825c', 700: '#09694c',
          800: '#09533e', 900: '#084536',
        },
      },
      fontFamily: { sans: ['DM Sans', 'Noto Sans SC', 'system-ui', 'sans-serif'] },
      boxShadow: {
        card: '0 18px 48px rgba(3, 16, 12, 0.08)',
        glow: '0 16px 44px rgba(11, 130, 92, 0.24)',
      },
    },
  },
  plugins: [],
};
