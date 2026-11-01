import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served from https://ashwin-nat.github.io/dota2-integrations/
export default defineConfig({
  plugins: [react()],
  base: "/dota2-integrations/",
});
