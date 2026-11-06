import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        unfpa: {
          blue: '#00658C',
          light: '#0088BB',
          dark: '#004A66',
        },
        status: {
          on_track: '#1A7A5A',
          behind: '#CC6A00',
          critical: '#C7172E',
        },
      },
      fontFamily: {
        bangla: ['Hind Siliguri', 'Noto Sans Bengali', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
