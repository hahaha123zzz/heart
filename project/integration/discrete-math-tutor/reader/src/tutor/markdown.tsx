import React from 'react';
import ReactMarkdown from 'react-markdown-base';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

// 高亮只处理文本节点，代码、公式和 URL 不参与替换。
function remarkMark() {
  return function visit(node: any) {
    if (!node.children) return;
    node.children = node.children.flatMap((child: any) => {
      if (child.type !== 'text') { visit(child); return [child]; }
      const parts = []; let end = 0;
      for (const match of child.value.matchAll(/==([^=\n]+)==/g)) {
        parts.push({type: 'text', value: child.value.slice(end, match.index)});
        parts.push({type: 'strong', data: {hName: 'mark'}, children: [{type: 'text', value: match[1]}]});
        end = match.index + match[0].length;
      }
      parts.push({type: 'text', value: child.value.slice(end)});
      return parts;
    });
  };
}

export default function HostMarkdown({components, remarkPlugins, urlTransform, ...props}: any) {
  const InlineCode = components.code;
  const Link = components.a;
  return <ReactMarkdown {...props}
    remarkPlugins={[...remarkPlugins, remarkMath, remarkMark]}
    rehypePlugins={[[rehypeKatex, {trust: false, throwOnError: false, strict: 'ignore'}]]}
    urlTransform={(value: string, key: string, node: unknown) => {
      const safe = urlTransform(value, key, node);
      if (key !== 'href') return '';
      if (safe.startsWith('#')) return safe;
      try {
        const url = new URL(safe);
        if (['https:', 'http:'].includes(url.protocol) && !url.username && !url.password) return url.href;
      } catch { /* 相对地址不属于教材来源契约。 */ }
      return '';
    }}
    components={{...components,
      a: (props: any) => props.href ? <Link {...props} /> : <span>{props.children}</span>,
      // 上游基础组件把单行围栏当成行内代码；保留围栏的块级含义。
      code: ({children, className, ...props}: any) => String(children).endsWith('\n') || className?.startsWith('language-')
        ? <div className="md-code-block"><pre><code className={className}>{String(children).replace(/\n$/, '')}</code></pre></div>
        : <InlineCode {...props} className={className}>{children}</InlineCode>,
      img: ({alt}: any) => alt ? <span className="markdown-image-label">[图片：{alt}]</span> : null,
      input: ({checked}: any) => <input type="checkbox" checked={Boolean(checked)} disabled />,
    }} />;
}
