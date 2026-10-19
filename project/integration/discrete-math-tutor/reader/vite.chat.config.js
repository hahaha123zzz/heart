import { defineConfig } from 'vite';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const upstream = path.resolve(root, '../../../vendor/DeepTutor/web');
export default defineConfig({
  root,
  define: {'process.env.NODE_ENV': JSON.stringify('production')},
  resolve: {
    dedupe: ['react', 'react-dom', 'remark-gfm', 'katex'],
    alias: [
      {find: /^react-markdown$/, replacement: path.join(root, 'src/tutor/markdown.tsx')},
      {find: 'react-markdown-base', replacement: path.join(root, 'node_modules/react-markdown/index.js')},
      {find: '@/components/common/InlineFileCard', replacement: path.join(root, 'src/tutor/attachments.tsx')},
      {find: '@', replacement: upstream},
    ],
  },
  build: {
    outDir: '../frontend/tutor-markdown', emptyOutDir: true,
    lib: {entry: 'src/tutor/index.tsx', name: 'TutorMarkdown', formats: ['iife'], fileName: () => 'tutor-markdown.js', cssFileName: 'tutor-markdown'},
    rollupOptions: {output: {assetFileNames: '[name][extname]'}},
  },
  plugins: [{
    name: 'markdown-licenses',
    generateBundle(_, bundle) {
      const packages = new Set();
      for (const chunk of Object.values(bundle)) {
        for (const file of Object.keys(chunk.modules || {})) {
          const match = file.replaceAll('\\', '/').match(/\/node_modules\/((?:@[^/]+\/)?[^/]+)/);
          if (match) packages.add(match[1]);
        }
      }
      let notice = 'DeepTutor SimpleMarkdownRenderer and display/math utilities\n' +
        'HKUDS/DeepTutor @ 6cf793bd868ba5ecbe64722936d4be8fab5a01df\n' +
        'Host adapters: restricted URLs/media, mark syntax, scoped citation navigation.\n\n' +
        fs.readFileSync(path.resolve(upstream, '../LICENSE'), 'utf8');
      for (const name of [...packages].sort()) {
        const directory = path.join(root, 'node_modules', name);
        const metadata = JSON.parse(fs.readFileSync(path.join(directory, 'package.json'), 'utf8'));
        const licenses = fs.readdirSync(directory).filter(file => /^(licen[cs]e|copying|notice)(\.|$)/i.test(file));
        let text = licenses.map(file => fs.readFileSync(path.join(directory, file), 'utf8')).join('\n');
        if (!text && metadata.license === 'MIT') {
          const readme = fs.readFileSync(path.join(directory, 'readme.md'), 'utf8');
          const declaration = readme.match(/## License\s+([\s\S]*?)(?=\n## |\n<!--|$)/)?.[1];
          const mit = fs.readFileSync(path.join(root, 'node_modules/react/LICENSE'), 'utf8');
          if (declaration) text = declaration + '\nCopyright: ' + metadata.author + '\n\n' + mit.slice(mit.indexOf('Permission is hereby'));
        }
        if (!text) throw new Error(`缺少打包依赖许可：${name}`);
        notice += `\n\n--- ${name} ${metadata.version} ---\n` + text;
      }
      this.emitFile({type: 'asset', fileName: 'THIRD_PARTY_NOTICES.txt', source: notice});
    },
  }],
});
