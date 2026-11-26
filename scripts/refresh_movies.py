"""Resolve unambiguous scheduled films using TMDB. No credentials in output."""
import json, os, re, time, unicodedata, urllib.request, urllib.parse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if c.isalnum())
def query(row):
    title = re.sub(r'^\s*\[[^\]]+\]\s*', '', row['title']).strip()
    match = re.search(r'\(([A-Za-z][^()]+)\)\s*$', title)
    explicit = any(re.search(r'ταινί|κινηματογρ|\bmovies?\b|\bfilms?\b', c, re.I) for c in row.get('categories', []))
    if not explicit and not (match and row['stop']-row['start']>=75*60000):
        return None
    return (match.group(1).strip() if match else title, str(row.get('year') or ''), explicit)
def select(results, title, year, kind):
    matches = {}
    for r in results:
        if r.get('media_type') != kind or r.get('adult') or not isinstance(r.get('id'),int):
            continue
        names = [r.get('title'),r.get('original_title'),r.get('name'),r.get('original_name')]
        if norm(title) not in [norm(n) for n in names if n]:
            continue
        date = r.get('release_date') or r.get('first_air_date') or ''
        if year and date[:4]!=year:
            continue
        matches[r['id']] = r
    return list(matches.values())
def trailer(videos):
    for v in videos:
        if v.get('official') is True and v.get('site')=='YouTube' and v.get('type')=='Trailer' and re.fullmatch(r'[A-Za-z0-9_-]{11}',str(v.get('key',''))):
            return v['key']
    return None
def api(path,token,**params):
    url='https://api.themoviedb.org/3/'+path+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=12) as res:
        return json.load(res)
def resolve(row,token):
    q=query(row)
    if not q: return None
    title,year,explicit=q
    results=api('search/multi',token,query=title,language='en-US',include_adult='false').get('results',[])
    movies=select(results,title,year,'movie')
    tv=select(results,title,year,'tv')
    if len(movies)!=1 or (tv and not explicit): return None
    m=movies[0]
    rating=m.get('vote_average')
    votes=m.get('vote_count')
    if not isinstance(rating,(int,float)) or not 0<=rating<=10 or not isinstance(votes,int) or votes<0: return None
    videos=api('movie/'+str(m['id'])+'/videos',token,language='en-US').get('results',[])
    return dict(id=m['id'],vote_average=rating,vote_count=votes,trailer=trailer(videos))
def main():
    token=os.environ.get('TMDB_READ_TOKEN','').strip()
    if not token:
        print('TMDB not configured; leaving existing schedule untouched.')
        return
    schedule=json.loads((ROOT/'data/schedule.json').read_text())
    output={}
    seen=set()
    for row in schedule['rows']:
        key=row['title']+'|'+str(row.get('year') or '')
        if key in seen or not query(row): continue
        seen.add(key)
        result=resolve(row,token)
        if result: output[key]=result
        time.sleep(.15)
    target=ROOT/'data/movies.json'
    target.write_text(json.dumps({'at':int(time.time()*1000),'schedule_at':schedule['at'],'movies':output},ensure_ascii=False,indent=2)+'\n')
    print(f'Matched {len(output)} of {len(seen)} candidate titles.')
if __name__=='__main__': main()
