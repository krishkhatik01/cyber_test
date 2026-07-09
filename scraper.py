import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from supabase import create_client, Client

# Supabase Connection Setup
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_and_split_data(row_text):
    date_pattern = r'(\d{2})/(\d{2})/(\d{4})'
    match = re.search(date_pattern, row_text)
    
    parsed_date = None
    if match:
        day, month, year = match.group(1), match.group(2), match.group(3)
        # Supabase 'date' type YYYY-MM-DD format leta hai
        parsed_date = f"{year}-{month}-{day}"
        clean_title = row_text.replace(match.group(0), "").strip()
    else:
        clean_title = row_text.strip()
        
    clean_title = re.sub(r'^[—\s•.-]+|[—\s•.-]+$', '', clean_title).strip()
    
    vac_match = re.search(r'(\d+)\s*(?:जागांसाठी|पदांची|seats|vacancies)', clean_title)
    vacancies = vac_match.group(1) if vac_match else "Various"
    
    return clean_title, parsed_date, vacancies

def delete_expired_jobs():
    """Yeh function aaj ki date se purani saari jobs ko delete kar dega"""
    today_str = date.today().isoformat() # Aaj ki date (YYYY-MM-DD)
    print(f"\n🗑️ Expired jobs check ho rahi hain... (Today's Date: {today_str})")
    
    try:
        # Supabase query: Jo jobs ki last_date aaj se choti (lt) hai, unhe delete karo
        response = supabase.table("job_updates").delete().lt("last_date", today_str).execute()
        deleted_count = len(response.data) if response.data else 0
        print(f"✅ Cleanup Done! Total {deleted_count} expired jobs automatic delete ho gayin.")
    except Exception as e:
        print(f"❌ Auto-Delete Error: {e}")

def scrape_page_data(url, page_name):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    print(f"\n🔄 {page_name} se data fetch ho raha hai...")
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Connection Fail: {response.status_code}")
            return 0
    except Exception as e:
        print(f"❌ Request Error: {e}")
        return 0
        
    soup = BeautifulSoup(response.text, 'html.parser')
    all_tables = soup.find_all('table')
    
    if not all_tables:
        return 0

    inserted_count = 0
    
    for job_table in all_tables:
        rows = job_table.find_all('tr')
        
        for row in rows:
            full_row_text = row.text.strip()
            link_tag = row.find('a')
            
            if link_tag and full_row_text:
                job_url = link_tag['href']
                if job_url.startswith('/'):
                    job_url = f"https://www.majhinaukri.in{job_url}"
                    
                title, last_date, vacancies = clean_and_split_data(full_row_text)
                
                if len(title) > 12 and not any(x in job_url for x in ["/category/", "/contact-us/", "javascript:", "/share-"]):
                    
                    job_data = {
                        "title": title,
                        "form_name": title,
                        "vacancies": vacancies,
                        "category": "General",
                        "last_date": last_date, # Agar date nahi mili toh yeh NULL (None) rahega aur delete nahi hoga
                        "eligibility": "See Details",
                        "file_url": job_url,
                        "status": "Active"
                    }
                    
                    try:
                        existing = supabase.table("job_updates").select("*").eq("title", title).execute()
                        
                        if len(existing.data) == 0:
                            supabase.table("job_updates").insert(job_data).execute()
                            print(f"✅ Saved: {title}")
                            inserted_count += 1
                    except Exception as e:
                        print(f"❌ Supabase Insertion Error: {e}")
                        
    return inserted_count

def run_production_scraper():
    # 1. Naya data fetch aur insert karo
    home_count = scrape_page_data("https://www.majhinaukri.in/", "Homepage")
    rec_count = scrape_page_data("https://majhinaukri.in/current-recruitment/", "Current Recruitment Page")
    print(f"\n🚀 Naye records add hue: {home_count + rec_count}")
    
    # 2. Kaam khatam hone ke baad expired waali saari rows delete kar do
    delete_expired_jobs()

if __name__ == "__main__":
    run_production_scraper()