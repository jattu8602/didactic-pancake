"""
NSUT Scraper v2 — concurrent profile scraping
Uses Playwright to render JS, extracts emails from [at] obfuscation
"""
import asyncio
import re
import json
from playwright.async_api import async_playwright

BASE = 'https://www.nsut.ac.in'

DEPT_IDS = {
    28: 'Biological Sciences (Main)', 29: 'Chemistry (East)',
    30: 'Civil Engineering (West)', 31: 'Chemistry (Main)',
    32: 'CSE (East)', 33: 'CSE (Main)',
    34: 'Electrical Engineering', 35: 'ECE (East)',
    36: 'ECE (Main)', 38: 'Humanities (East)',
    39: 'Humanities (Main)', 40: 'Information Technology',
    42: 'Instrumentation & Control', 43: 'Management Studies',
    45: 'Mathematics', 46: 'Mechanical Engineering (Main)',
    47: 'Mechanical Engineering (West)', 49: 'Physics',
    113: 'Personality Development', 114: 'Design',
    115: 'Architecture & Planning', 118: 'Innovation & Entrepreneurship',
    119: 'Geoinformatics (West)',
}

def decode_emails(text):
    return [m.replace('[at]', '@').replace('[dot]', '.')
            for m in re.findall(r'[\w.+-]+(?:\[at\])[\w.-]+(?:\[dot\]\w+)+', text)]

async def collect_professors(browser):
    """Visit all department pages and collect professor names + profile URLs."""
    page = await browser.new_page(ignore_https_errors=True)
    all_profs = []
    
    for dept_id, dept_name in sorted(DEPT_IDS.items()):
        url = f'{BASE}/en/department/faculty/{dept_id}'
        try:
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(2000)
            profs = await page.evaluate('''() => {
                const rows = document.querySelectorAll("table.views-table tbody tr");
                return Array.from(rows).map(row => {
                    const nameTd = row.querySelector(".views-field-field-name");
                    const linkTd = row.querySelector(".views-field-view-node a");
                    if (!nameTd || !linkTd) return null;
                    return {
                        name: nameTd.innerText.trim(),
                        url: "https://www.nsut.ac.in" + linkTd.getAttribute("href")
                    };
                }).filter(Boolean);
            }''')
            if profs:
                print(f'  Dept {dept_id:3d} ({dept_name:35s}): {len(profs)} profs', flush=True)
                all_profs.extend(profs)
        except Exception as e:
            print(f'  Dept {dept_id:3d} ({dept_name:35s}): SKIP {str(e)[:40]}', flush=True)
    
    await page.close()
    return all_profs

async def scrape_profile(context, profile_url, semaphore):
    """Scrape a single profile page for email. Uses semaphore for concurrency control."""
    async with semaphore:
        page = await context.new_page()
        try:
            await page.goto(profile_url, timeout=15000)
            await page.wait_for_timeout(1500)
            text = await page.inner_text('body')
            decoded = decode_emails(text)
            return decoded[0] if decoded else ''
        except:
            return ''
        finally:
            await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--ignore-certificate-errors']
        )
        
        # Step 1: Collect all professors
        print('Step 1: Collecting professors from all departments...', flush=True)
        all_profs = await collect_professors(browser)
        print(f'Total professors: {len(all_profs)}', flush=True)
        
        # Step 2: Scrape profiles concurrently
        print('\nStep 2: Extracting emails from profiles (concurrent)...', flush=True)
        context = await browser.new_context(ignore_https_errors=True, user_agent='Mozilla/5.0')
        semaphore = asyncio.Semaphore(10)  # 10 concurrent connections
        
        tasks = [scrape_profile(context, p['url'], semaphore) for p in all_profs]
        emails = await asyncio.gather(*tasks)
        
        for i, email in enumerate(emails):
            all_profs[i]['email'] = email
            if (i + 1) % 50 == 0:
                found = sum(1 for e in emails[:i+1] if e)
                print(f'  Progress: {i+1}/{len(all_profs)} (found {found} emails)', flush=True)
        
        await context.close()
        
        found = sum(1 for e in emails if e)
        all_emails = set(e for e in emails if e)
        print(f'Done. {found}/{len(all_profs)} with emails ({len(all_emails)} unique)', flush=True)
        
        result = {
            'url': BASE,
            'professors': [{'name': p['name'], 'email': p['email'], 'phone': ''} for p in all_profs],
            'all_emails': sorted(all_emails),
            'all_phones': [],
            'statistics': {'total': len(all_profs), 'with_email': found},
        }
        
        with open('scraper_output/nsut.json', 'w') as f:
            json.dump(result, f, indent=2)
        
        print('Saved to scraper_output/nsut.json', flush=True)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
