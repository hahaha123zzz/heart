import {createContext} from 'react';

export const MarkdownContext = createContext({literals: [] as [string, string][]});

// 上游会展开反引号引用；先保护代码/数学/链接和数值数组，宿主解析前还原。
export function protectLiterals(text: string) {
  let prefix = 'TUTORLITERAL';
  while (text.includes(prefix)) prefix += 'X';
  const literals: [string, string][] = [];
  const content = text.replace(/```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)|`+[^`\n]*`+|\$\$[\s\S]*?(?:\$\$|$)|\$[^$\n]+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|!?\[[^\]\n]*\]\([^\n)]*\)|\[\s*\d+(?:\s*[,，]\s*\d+)+\s*\]/g, literal => {
    const key = prefix + literals.length + 'END';
    literals.push([key, literal]);
    return key;
  });
  return {content, literals};
}
