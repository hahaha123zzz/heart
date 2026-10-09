def block_text(b):
 def text(parts):return ''.join(p.get('text','') if p['type'] in ('text','symbol') else text(p.get('segments',[])) if 'segments' in p else '￼' for p in parts)
 if b['type']=='table':return '\n'.join(' | '.join(''.join(text(p) for p in c['paragraphs']) for c in row if not c.get('hidden')) for row in b['rows'])
 return text(b.get('segments',[]))
