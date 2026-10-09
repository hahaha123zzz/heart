import { defineConfig } from 'vite';
import fs from 'node:fs';
import path from 'node:path';
export default defineConfig({define:{'process.env.NODE_ENV':JSON.stringify('production')},base:'/static/pdf-reader/',build:{outDir:'../frontend/pdf-reader',emptyOutDir:true,
 lib:{entry:'src/reader.jsx',name:'TextbookPDF',formats:['es'],fileName:'reader'},
 rollupOptions:{output:{assetFileNames:'[name][extname]'}}},plugins:[{name:'local-pdf-resources',closeBundle(){
 const target=path.resolve('../frontend/pdf-reader');
 fs.copyFileSync('THIRD_PARTY_NOTICES.md',target+'/THIRD_PARTY_NOTICES.md');
 fs.copyFileSync('node_modules/pdfjs-dist/build/pdf.worker.min.mjs',target+'/pdf.worker.min.mjs');
 for(const dir of ['cmaps','standard_fonts']) fs.cpSync('node_modules/pdfjs-dist/'+dir,target+'/'+dir,{recursive:true});
}}]});
