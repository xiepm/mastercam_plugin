"""Bounded local retrieval with source paths; no vector database required."""
from pathlib import Path
import re
from .common import ROOT, load

def search(query, limit=8):
    if not query.strip() or not 1 <= limit <= 20:
        raise ValueError('Provide a query and limit between 1 and 20')
    terms = re.findall(r'[a-z0-9_.-]+|[\u4e00-\u9fff]+', query.casefold())
    # Add bounded bigrams for Chinese questions without word separators.
    phrases=[t for t in terms if re.fullmatch(r'[\u4e00-\u9fff]+',t)]
    terms=list(dict.fromkeys(terms+[t[i:i+2] for t in phrases for i in range(len(t)-1)]))[:64]
    results = []
    for item in load(ROOT/'ai/knowledge/index.json')['documents']:
        path = (ROOT/item['path']).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Knowledge path escapes package')
        body = path.read_text(encoding='utf-8-sig')
        haystack = (item['title']+' '+ ' '.join(item['tags'])+' '+body).casefold()
        score = sum(haystack.count(t) for t in terms)
        if score:
            lines = body.splitlines()
            matches = [(i+1,s) for i,s in enumerate(lines) if any(t in s.casefold() for t in terms)]
            results.append({'title':item['title'],'path':item['path'],'score':score,
                            'matches':[{'line':i,'text':s[:600]} for i,s in matches[:5]],
                            'status':item['status']})
    return sorted(results, key=lambda r:(-r['score'],r['path']))[:limit]

def read(path, start_line=1, max_lines=100):
    if path not in {x['path'] for x in load(ROOT/'ai/knowledge/index.json')['documents']}:
        raise ValueError('Select an indexed path from mc_knowledge_search')
    if start_line < 1 or not 1 <= max_lines <= 150:
        raise ValueError('Invalid line window')
    lines = (ROOT/path).read_text(encoding='utf-8-sig').splitlines()
    return {'path':path,'start_line':start_line,'total_lines':len(lines),
            'text':'\n'.join(lines[start_line-1:start_line-1+max_lines])}
