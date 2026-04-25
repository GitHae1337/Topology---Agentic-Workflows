/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: {
          bg: '#0a0a0a',
          dark: '#141414',
          border: '#262626',
          hover: '#333333',
        },
      },
    },
  },
  plugins: [],
}
