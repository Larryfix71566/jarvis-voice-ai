import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // Three entries (side-drawer plan D39, extended by
      // MORTIMER_DRAWER_POPOUT_PLAN.md DP1 for the drawer window): the
      // main console, the popped-out display window, and the popped-out
      // drawer window. Kept as separate module graphs on purpose —
      // displayMain.tsx and drawerMain.tsx must never pull in
      // jarvisClient.ts's load-time side effects (mic constraint
      // patching, PipecatClient construction). In dev this doesn't
      // matter (Vite serves any HTML file directly); this only affects
      // `npm run build`.
      input: {
        main: resolve(__dirname, 'index.html'),
        display: resolve(__dirname, 'display.html'),
        drawer: resolve(__dirname, 'drawer.html'),
      },
    },
  },
})
