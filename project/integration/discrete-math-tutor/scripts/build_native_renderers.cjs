// 构建使用固定副本的前端源码；第三方依赖只在构建时读取。
const path=require('path'),fs=require('fs'),crypto=require('crypto');
const root=path.resolve(__dirname,'..'),vendor=path.resolve(root,'../../vendor/DeepTutor/web');
const deps=path.resolve(process.env.DEEPTUTOR_WEB_DEPS || 'D:/deeptutor/web');
process.env.DEEPTUTOR_WEB_DEPS=deps;
const {webpack}=require(require.resolve('next/dist/compiled/webpack/webpack',{paths:[deps]}));
const output=path.join(root,'frontend/vendor/deeptutor-renderers');
const compiler=webpack({mode:'production',entry:path.join(root,'frontend/native/entry.tsx'),
 output:{path:output,filename:'viewer.js',chunkFilename:'[name].[contenthash:12].js',publicPath:'/static/vendor/deeptutor-renderers/'},
 resolve:{extensions:['.tsx','.ts','.js','.json'],modules:[path.join(deps,'node_modules'),'node_modules'],alias:{
  'next/dynamic$':path.join(root,'frontend/native/dynamic.tsx'),
  'react-i18next$':path.join(root,'frontend/native/translation.ts'),
  '@/lib/api$':path.join(root,'frontend/native/api.ts'),'@':vendor}},
 module:{rules:[{test:/\.tsx?$/,exclude:/node_modules/,use:path.join(root,'scripts/native-typescript-loader.cjs')},
  {test:/\.css$/,use:path.join(root,'scripts/native-css-loader.cjs')}]},
 optimization:{minimize:false},performance:{hints:false}});
compiler.run((err,stats)=>{
 compiler.close(()=>{});
 if(err || stats.hasErrors()){console.error(err || stats.toString({all:false,errors:true}));process.exitCode=1;return;}
 const files=[...stats.compilation.fileDependencies].filter(name=>name.startsWith(vendor) && fs.statSync(name).isFile());
 const sources=files.map(name=>({path:path.relative(vendor,name).replaceAll('\\','/'),sha256:crypto.createHash('sha256').update(fs.readFileSync(name)).digest('hex')}));
 fs.writeFileSync(path.join(output,'SOURCE_NOTICE.json'),JSON.stringify({upstream:'DeepTutor',commit:'6cf793bd868ba5ecbe64722936d4be8fab5a01df',
  source_root:'project/vendor/DeepTutor/web',sources,assets:[...stats.compilation.assetsInfo.keys()]},null,2));
 const postcss=require(require.resolve('postcss',{paths:[deps]}));
 const tailwind=require(require.resolve('tailwindcss',{paths:[deps]}));
 const prefix='.native-viewer{--border:#d7dedb;--background:#fff;--card:#fff;--foreground:#1e2926;--muted-foreground:#65716c;}\n.native-viewer iframe{width:100%;}.native-viewer *{box-sizing:border-box;}\n';
 postcss([tailwind({content:files.filter(name=>/\.tsx$/.test(name)),corePlugins:{preflight:false},theme:{extend:{}}})])
  .process('@tailwind utilities;',{from:undefined}).then(result=>{
   fs.writeFileSync(path.join(output,'viewer.css'),prefix+result.css);
   console.log(JSON.stringify({sources:sources.length,assets:stats.compilation.assetsInfo.size,output}));
  }).catch(error=>{console.error(error);process.exitCode=1;});
});
