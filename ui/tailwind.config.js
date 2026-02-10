
/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                'claw-bg': '#E0E7FF', // Periwinkle/Lavender Mist
                'claw-border': '#000000', // Sharp black
                'claw-red': '#FF0000', // Glitch/Paranoia
            },
            fontFamily: {
                sans: ['Arial', 'Inter', 'sans-serif'],
            },
            boxShadow: {
                'sharp': '2px 2px 0px 0px rgba(0,0,0,1)',
            }
        },
    },
    plugins: [],
}
