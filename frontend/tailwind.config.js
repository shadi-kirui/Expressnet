/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        app: {
          bg: '#ffffff',
          navy: 'var(--dashboard-color)',
          navySoft: 'var(--dashboard-color-soft)',
          accent: 'var(--dashboard-color)',
          accentDark: 'var(--dashboard-color-soft)',
        },
        sidebar: 'var(--dashboard-color)',
      },
      boxShadow: {
        soft: 'none',
      },
    },
  },
  plugins: [],
};
