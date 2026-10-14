// 将固定依赖与许可证复制到静态目录，运行时不访问 CDN。
const fs = require('node:fs');
const path = require('node:path');
const target = path.resolve(__dirname, '../frontend/vendor/cytoscape');
fs.mkdirSync(target, {recursive:true});
fs.copyFileSync(require.resolve('cytoscape/dist/cytoscape.min.js'), path.join(target, 'cytoscape.min.js'));
fs.copyFileSync(path.join(__dirname, 'node_modules/cytoscape/LICENSE'), path.join(target, 'LICENSE'));
