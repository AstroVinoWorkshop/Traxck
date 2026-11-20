import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import legacy from '@vitejs/plugin-legacy';

export default defineConfig({
  plugins:[react(),legacy({targets:['ios_saf >= 12'],polyfills:true})],
  server:{proxy:{'/api':'http://127.0.0.1:8768'}}
});