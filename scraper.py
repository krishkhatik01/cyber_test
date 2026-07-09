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
    # Date nikalne ke liye pattern (DD/MM/YYYY)
    date_pattern = r'\b\d{2}/\d{2}/\d{4}\b'
    match = re.search(date_pattern, row_text)
    
    if match:
        last_date = match.group(0)
        clean_title = row_text.replace(last_date, "").strip()
    else:
        last_date = "Check Notification"
        clean_title = row_text.strip()
        
    # Title ke aage-piche se faltu dashes ya dots hatana
    clean_title = re.sub(r'^[—\s•.-]+|[—\s•.-]+$', '', clean_title).strip()
    return clean_title, last_date

def scrape_page_data(url, page_name):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    print(f"\n🔄 {page_name} se data fetch ho raha hai: {url}")
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Website connect nahi ho pai. Status: {response.status_code}")
            return 0
    except Exception as e:
        print(f"❌ HTTP Request Error: {e}")
        return 0
        
    soup = BeautifulSoup(response.text, 'html.parser')
    all_tables = soup.find_all('table')
    
    if not all_tables:
        print(f"⚠️ {page_name} par koi table nahi mila!")
        return 0

    print(f"Total {len(all_tables)} tables mile. Rows check ho rahi hain...")
    inserted_count = 0
    
    for job_table in all_tables:
        rows = job_table.find_all('tr')
        
        for row in rows:
            full_row_text = row.text.strip()
            link_tag = row.find('a')
            
            if link_tag and full_row_text:
                job_url = link_tag['href']
                
                # Relative links ko absolute banana
                if job_url.startswith('/'):
                    job_url = f"https://www.majhinaukri.in{job_url}"
                    
                title, last_date = clean_and_split_data(full_row_text)
                
                # Faltu ke pages aur menus ko filter out karna
                if len(title) > 15 and not any(x in job_url for x in ["/category/", "/contact-us/", "javascript:", "/share-", "/privacy-policy/"]):
                    
                    job_data = {
                        "title": title,
                        "last_date": last_date,
                        "apply_link": job_url
                    }
                    
                    try:
                        # Database me check karo ki yeh job pehle se toh nahi hai
                        existing = supabase.table("jobs").select("*").eq("title", title).execute()
                        
                        if len(existing.data) == 0:
                            supabase.table("jobs").insert(job_data).execute()
                            print(f"✅ Saved: {title}")
                            inserted_count += 1
                        else:
                            # Pehle se hai toh skip kar do (No Duplicates)
                            pass
                            
                    except Exception as e:
                        print(f"❌ Supabase Error: {e}")
                        
    return inserted_count

def run_production_scraper():
    # 1. Pehle Homepage ka data nikalenge
    homepage_url = "https://www.majhinaukri.in/"
    home_count = scrape_page_data(homepage_url, "Homepage")
    
    # 2. Phir Current Recruitment wale page ka saara data nikalenge
    recruitment_url = "https://majhinaukri.in/current-recruitment/"
    rec_count = scrape_page_data(recruitment_url, "Current Recruitment Page")
    
    print(f"\n🚀 [Scraping Done] Homepage se {home_count} aur Recruitment page se {rec_count} naye jobs mile!")

if __name__ == "__main__":
    run_production_scraper()