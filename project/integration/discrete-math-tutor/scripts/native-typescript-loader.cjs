const ts=require(require.resolve('typescript',{paths:[process.env.DEEPTUTOR_WEB_DEPS]}));
module.exports=function(source){return ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,
 module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true},fileName:this.resourcePath}).outputText;};
