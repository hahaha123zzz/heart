import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server.browser';
import SimpleMarkdownRenderer from '@/components/common/SimpleMarkdownRenderer';
import { processMarkdownContent } from '@/lib/latex';
// 复用宿主已加载的 reader.css 与同一版本 KaTeX，避免重复打包字体。
import './style.css';

export function render(text: string) {
  return renderToStaticMarkup(<SimpleMarkdownRenderer content={processMarkdownContent(String(text))}
    variant="compact" className="tutor-markdown answer-text" />);
}

if (typeof document !== 'undefined') document.addEventListener('click', event => {
  const anchor = (event.target as Element)?.closest?.('.tutor-markdown a');
  if (!anchor) return;
  const href = anchor.getAttribute('href');
  if (!href?.startsWith('#')) return;
  event.preventDefault();
  const markdown = anchor.closest('.tutor-markdown');
  if (anchor.closest('.citation-group')) {
    const number = anchor.textContent?.trim();
    if (!/^\d+$/.test(number || '')) return;
    const scope = markdown?.closest('.message-body,.exercise-help,.exercise-feedback');
    // 引用只触发同条回答已有的来源按钮，继续经过原版本与证据检查。
    scope?.querySelector<HTMLButtonElement>(`.message-source[data-source-index="${Number(number) - 1}"]`)?.click();
    return;
  }
  try {
    const id = decodeURIComponent(href.slice(1));
    [...(markdown?.querySelectorAll<HTMLElement>('[id]') || [])].find(node => node.id === id)?.scrollIntoView({block: 'nearest'});
  } catch { /* 无效锚点保持为普通文本，不跨消息导航。 */ }
});
