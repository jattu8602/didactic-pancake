import requests
import re
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

def extract_phones(text):
    phones = re.findall(r'(?:\+?91[-.\s]?)?[789]\d{9}|(?:\+?91[-.\s]?)?0?[789]\d{9}', text)
    phones += re.findall(r'\d{3,4}[-.\s]?\d{6,8}', text)
    return list(set(p.strip() for p in phones if len(p.strip()) >= 10))

def extract_emails(text):
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    return list(set(e.lower() for e in emails if not e.lower().endswith(('.png', '.jpg', '.gif', '.css', '.js'))))

def scrape_website(url, timeout=15):
    result = {'url': url, 'phones': [], 'emails': [], 'pages_scraped': 0, 'error': None}
    visited = set()
    
    try:
        resp = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code != 200:
            result['error'] = f'HTTP {resp.status_code}'
            return result
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text()
        result['phones'] = extract_phones(text)
        result['emails'] = extract_emails(text)
        result['pages_scraped'] = 1
        
        contact_links = []
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            if any(kw in href for kw in ['contact', 'about', 'phone', 'email']):
                contact_links.append(urljoin(url, a['href']))
        
        for link in list(set(contact_links))[:3]:
            if link in visited:
                continue
            visited.add(link)
            try:
                cr = requests.get(link, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
                if cr.status_code == 200:
                    cs = BeautifulSoup(cr.text, 'html.parser')
                    ct = cs.get_text()
                    result['phones'].extend(extract_phones(ct))
                    result['emails'].extend(extract_emails(ct))
                    result['pages_scraped'] += 1
            except:
                pass
        
        result['phones'] = list(set(result['phones']))
        result['emails'] = list(set(result['emails']))
        
    except Exception as e:
        result['error'] = str(e)
    
    return result

if __name__ == '__main__':
    with open('/tmp/ugc_all.json') as f:
        ugc = json.load(f)['List']
    
    test = []
    for u in ugc:
        if u.get('url') and len(test) < 5:
            test.append(u)
        if len(test) == 5:
            break
    
    results = []
    for u in test:
        print(f"\n=== {u['uni_name']} ({u['state']}) ===")
        print(f"URL: {u['url']}")
        r = scrape_website(u['url'])
        print(f"  Pages: {r['pages_scraped']}, Phones: {r['phones'][:5]}, Emails: {r['emails'][:5]}")
        if r['error']:
            print(f"  Error: {r['error']}")
        results.append({
            'name': u['uni_name'],
            'state': u['state'].strip(),
            'url': u['url'],
            'scraped': r
        })
    
    with open('/tmp/ugc_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nDone! Results saved to /tmp/ugc_test_results.json")
