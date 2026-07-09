import os
import re
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# Supabase Connection Setup
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_and_split_data(row_text):
    date_pattern = r'\b\d{2}/\d{2}/\d{4}\b'
    match = re.search(date_pattern, row_text)
    
    if match:
        last_date = match.group(0)
        clean_title = row_text.replace(last_date, "").strip()
    else:
        last_date = "Check Notification"
        clean_title = row_text.strip()
        
    clean_title = re.sub(r'^[—\s•.-]+|[—\s•.-]+$', '', clean_title).strip()
    return clean_title, last_date

def run_production_scraper():
    url = "https://www.majhinaukri.in/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    print("Live MajhiNaukri se data fetch ho raha hai...")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Website connect nahi ho pai. Status: {response.status_code}")
        return
        
    soup = BeautifulSoup(response.text, 'html.parser')
    job_table = soup.find('table')
    
    if not job_table:
        print("Table nahi mila!")
        return

    rows = job_table.find_all('tr')
    print(f"Total rows mile: {len(rows)}")
    
    inserted_count = 0
    for row in rows:
        full_row_text = row.text.strip()
        link_tag = row.find('a')
        
        if link_tag and full_row_text:
            job_url = link_tag['href']
            
            # Agar relative URL hai toh base domain jod denge
            if job_url.startswith('/'):
                job_url = f"https://www.majhinaukri.in{job_url}"
                
            title, last_date = clean_and_split_data(full_row_text)
            
            # Faltu menu links hatane ke liye sirf length check karenge (robust filtering)
            if len(title) > 12 and not any(x in job_url for x in ["/category/", "/contact-us/", "javascript:"]):
                
                job_data = {
                    "title": title,
                    "last_date": last_date,
                    "apply_link": job_url
                }
                
                try:
                    existing = supabase.table("jobs").select("*").eq("title", title).execute()
                    
                    if len(existing.data) == 0:
                        supabase.table("jobs").insert(job_data).execute()
                        print(f"✅ Saved: {title}")
                        inserted_count += 1
                    else:
                        print(f"⏭️ Skipped: {title}")
                        
                except Exception as e:
                    print(f"❌ Supabase Error: {e}")
                    
    print(f"Total {inserted_count} naye records save hue.")

if __name__ == "__main__":
    run_production_scraper()