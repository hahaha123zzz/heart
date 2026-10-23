import React, {useContext} from 'react';
import ReactMarkdown from 'react-markdown-base';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import {MarkdownContext} from './context';

// 上游为避免与强调混淆会跳过 **术语**[n]；仅补齐 AST 正文节点中的引用。
function remarkCitations() {
  return function visit(node: any) {
    if (!node.children || ['link', 'code', 'inlineCode', 'math', 'inlineMath', 'image'].includes(node.type)) return;
    node.children = node.children.flatMap((child: any) => {
      if (child.type !== 'text') { visit(child); return [child]; }
      const parts: any[] = []; let end = 0;
      for (const match of child.value.matchAll(/\[(\d+)\]/g)) {
        parts.push({type: 'text', value: child.value.slice(end, match.index)});
        parts.push({type: 'link', url: '#references', title: 'citation', children: [{type: 'text', value: match[1]}]});
        end = match.index + match[0].length;
      }
      parts.push({type: 'text', value: child.value.slice(end)});
      return parts;
    });
  };
}

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
  const {literals, media} = useContext(MarkdownContext);
  const validMedia = media.filter(item => /^[a-f0-9]{64}$/.test(item.sha256 || '')
    && /^[a-f0-9]{64}$/.test(item.version || '') && item.document_id
    && item.image_url === `/api/figures/${item.id}/image?sha256=${item.sha256}&version=${item.version}&document_id=${encodeURIComponent(item.document_id)}`
    && /^(?:figure|formula|image)-\d+-\d+$/.test(item.id || ''));
  let content = String(props.children || '');
  // 回调返回原文，避免替换字符串中的 $$、$& 被 JavaScript 再解释。
  for (const [key, literal] of literals) content = content.replaceAll(key, () => literal);
  const InlineCode = components.code;
  const Link = components.a;
  return <ReactMarkdown {...props}
    remarkPlugins={[...remarkPlugins, remarkMath, remarkMark, remarkCitations]}
    rehypePlugins={[[rehypeKatex, {trust: false, throwOnError: false, strict: 'ignore'}]]}
    urlTransform={(value: string, key: string, node: unknown) => {
      if (key === 'src' && validMedia.some(item => value === `media:${item.id}`)) return value;
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
      a: (props: any) => {
        const label = String(props.children || '');
        if (props.title === 'citation' && props.href === '#references' && /^\d+$/.test(label)) {
          return <sup className="citation-group"><button type="button" data-tutor-citation={label}
            aria-label={`查看来源 ${label}`}>{label}</button></sup>;
        }
        return props.href ? <Link {...props} /> : <span>{props.children}</span>;
      },
      // 上游基础组件把单行围栏当成行内代码；保留围栏的块级含义。
      code: ({children, className, ...props}: any) => String(children).endsWith('\n') || className?.startsWith('language-')
        ? <div className="md-code-block"><pre><code className={className}>{String(children).replace(/\n$/, '')}</code></pre></div>
        : <InlineCode {...props} className={className}>{children}</InlineCode>,
      img: ({alt, src}: any) => {
        const item = validMedia.find(item => src === `media:${item.id}`);
        if (!item) return alt ? <span className="markdown-image-label">[图片：{alt}]</span> : null;
        return <span className="textbook-figure answer-media">
          <a href={item.image_url} target="_blank" rel="noopener noreferrer"><img src={item.image_url} alt={item.label || alt} loading="lazy" /></a>
          <span className="answer-media-caption">{item.label} · {item.review_status === 'approved' ? '已审核' : '待审核'}
            <button type="button" data-tutor-media={item.id}>{item.location_status === 'section' ? '打开所在小节' : item.location_status === 'caption' ? '查看图注位置' : '返回教材'}</button></span>
        </span>;
      },
      input: ({checked}: any) => <input type="checkbox" checked={Boolean(checked)} disabled />,
    }}>{content}</ReactMarkdown>;
}
