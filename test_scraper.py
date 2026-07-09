import os
import re
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# Supabase Connection Setup (Environment variables se data uthaega)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_and_split_data(row_text):
    # Regex jo DD/MM/YYYY format ki date dhoondega
    date_pattern = r'\b\d{2}/\d{2}/\d{4}\b'
    match = re.search(date_pattern, row_text)
    
    if match:
        last_date = match.group(0)
        clean_title = row_text.replace(last_date, "").strip()
    else:
        last_date = "Check Notification"
        clean_title = row_text.strip()
        
    # Extra symbols jaise '—' ko saaf karna start ya end se
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
    
    for row in rows:
        full_row_text = row.text.strip()
        link_tag = row.find('a')
        
        if link_tag and full_row_text:
            job_url = link_tag['href']
            
            # Title aur Date split function
            title, last_date = clean_and_split_data(full_row_text)
            
            # Filter valid jobs
            if "majhinaukri.in" in job_url and len(title) > 10:
                
                # Supabase payload dictionary banana
                job_data = {
                    "title": title,
                    "last_date": last_date,
                    "apply_link": job_url
                }
                
                try:
                    # Duplicate check karna database me push karne se pehle
                    existing = supabase.table("jobs").select("*").eq("title", title).execute()
                    
                    if len(existing.data) == 0:
                        # Naya record insert karna
                        supabase.table("jobs").insert(job_data).execute()
                        print(f"✅ Database me save hua: {title} | Date: {last_date}")
                    else:
                        print(f"⏭️ Pehle se maujood hai: {title}")
                        
                except Exception as e:
                    print(f"❌ Supabase me error aaya: {e}")

if __name__ == "__main__":
    run_production_scraper()