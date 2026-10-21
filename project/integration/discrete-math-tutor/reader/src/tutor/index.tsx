import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server.browser';
import SimpleMarkdownRenderer from '@/components/common/SimpleMarkdownRenderer';
import { processMarkdownContent } from '@/lib/latex';
import {repairChineseEmphasis} from '@/lib/markdown-display';
import {MarkdownContext, protectLiterals} from './context';
// 复用宿主已加载的 reader.css 与同一版本 KaTeX，避免重复打包字体。
import './style.css';

export function render(text: string, {streaming = false, media = [] as any[]} = {}) {
  const protectedText = protectLiterals(processMarkdownContent(String(text)));
  return renderToStaticMarkup(<MarkdownContext.Provider value={{...protectedText, media}}>
    <div data-markdown-state={streaming ? 'streaming' : 'settled'}>
      <SimpleMarkdownRenderer content={repairChineseEmphasis(protectedText.content, 'zh')}
        variant="compact" className="tutor-markdown answer-text" />
    </div>
  </MarkdownContext.Provider>);
}

if (typeof document !== 'undefined') document.addEventListener('click', event => {
  const anchor = (event.target as Element)?.closest?.('.tutor-markdown a');
  if (!anchor) return;
  const href = anchor.getAttribute('href');
  if (!href?.startsWith('#')) return;
  event.preventDefault();
  const markdown = anchor.closest('.tutor-markdown');
  try {
    const id = decodeURIComponent(href.slice(1));
    [...(markdown?.querySelectorAll<HTMLElement>('[id]') || [])].find(node => node.id === id)?.scrollIntoView({block: 'nearest'});
  } catch { /* 无效锚点保持为普通文本，不跨消息导航。 */ }
});
