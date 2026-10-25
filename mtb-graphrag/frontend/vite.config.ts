import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            // Keep the shared rendering runtime separate from route modules.
            { name: 'react-runtime', test: /node_modules[\\/](?:react|react-dom|scheduler)[\\/]/ },
          ],
        },
      },
    },
  },
})
