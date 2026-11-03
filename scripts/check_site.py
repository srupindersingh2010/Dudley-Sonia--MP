"""Check generated documents, local targets and unsafe external URL schemes."""
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1]/'dist'
errors=[]
for file in ROOT.glob('*.html'):
 soup=BeautifulSoup(file.read_text(),'html.parser')
 if soup.html.get('lang')!='en':errors.append(f'{file.name}: missing language')
 if len(soup.find_all('h1'))!=1:errors.append(f'{file.name}: needs one h1')
 if not soup.find('main'):errors.append(f'{file.name}: missing main')
 ids=[el['id'] for el in soup.select('[id]')]
 if len(set(ids))!=len(ids):errors.append(f'{file.name}: duplicate ids')
 for img in soup.find_all('img'):
  if not img.get('alt'):errors.append(f'{file.name}: image lacks alternative text')
 for el in soup.select('[href],[src]'):
  url=el.get('href',el.get('src',''));parts=urlsplit(url)
  if parts.scheme and parts.scheme not in ['https','http','mailto','tel']:errors.append(f'{file.name}: unsafe URL')
  if not parts.scheme and not parts.netloc:
   target=ROOT/unquote(parts.path) if parts.path else file
   if not target.exists():errors.append(f'{file.name}: missing {parts.path}')
   if parts.fragment and target.suffix=='.html' and target.exists():
    other=BeautifulSoup(target.read_text(),'html.parser')
    if not other.find(id=parts.fragment):errors.append(f'{file.name}: missing fragment {url}')
if errors:raise SystemExit('\n'.join(errors))
print('All static pages pass document, local link, fragment, alt text and URL checks.')
