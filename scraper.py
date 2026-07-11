import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import date
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
        parsed_date = f"{year}-{month}-{day}"
        clean_title = row_text.replace(match.group(0), "").strip()
    else:
        clean_title = row_text.strip()

    clean_title = re.sub(r'^[—\s•.-]+|[—\s•.-]+$', '', clean_title).strip()

    vac_match = re.search(r'(\d+)\s*(?:जागांसाठी|पदांची|seats|vacancies)', clean_title)
    vacancies = vac_match.group(1) if vac_match else "Various"

    # FIX: vacancy phrase ko title se hata do, warna vacancy count
    # change hone par (e.g. 153 -> 132) same job duplicate ban jata hai
    # kyunki normalized_title alag ban jati thi.
    if vac_match:
        clean_title = clean_title.replace(vac_match.group(0), "").strip()
        clean_title = re.sub(r'^[—\s•.-]+|[—\s•.-]+$', '', clean_title).strip()
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    return clean_title, parsed_date, vacancies


def normalize_title(title: str) -> str:
    """Must mirror the Postgres generated column exactly:
    lower + trim + collapse whitespace."""
    t = title.strip().lower()
    t = re.sub(r'\s+', ' ', t)
    return t


def delete_expired_jobs():
    today_str = date.today().isoformat()
    print(f"\n🗑️ Expired jobs check ho rahi hain... (Today's Date: {today_str})")
    try:
        response = supabase.table("job_updates").delete().lt("last_date", today_str).execute()
        deleted_count = len(response.data) if response.data else 0
        print(f"✅ Cleanup Done! Total {deleted_count} expired jobs automatic delete ho gayin.")
    except Exception as e:
        print(f"❌ Auto-Delete Error: {e}")


def scrape_sidebar_section(soup, section_heading: str, category: str) -> list:
    """Sidebar ke Hall Ticket / Result / Admit Card sections scrape karo"""
    jobs = []

    # Section heading dhoondo
    heading = soup.find(lambda tag: tag.name in ['h2', 'h3', 'h4', 'div', 'span']
                         and section_heading in tag.text)
    if not heading:
        return jobs

    # Heading ke baad wale links lo
    parent = heading.find_parent()
    links = parent.find_all('a', href=True)

    for link in links:
        title = link.text.strip()
        url = link['href']

        if url.startswith('/'):
            url = f"https://www.majhinaukri.in{url}"

        if is_garbage(title) or len(title) < 15:
            continue
        if any(x in url for x in ["/category/", "/tag/", "javascript:", "/share-"]):
            continue

        jobs.append({
            "title": title,
            "form_name": title,
            "vacancies": "Various",
            "category": category,
            "last_date": None,
            "eligibility": "See Details",
            "file_url": url,
            "status": "Active"
        })

    return jobs


def upsert_jobs(jobs_list: list) -> int:
    inserted = 0
    seen_urls = set()

    for job_data in jobs_list:
        # file_url is the most reliable unique signal — two jobs with the
        # same URL are definitely the same posting, regardless of whether
        # the title text or vacancy count changed slightly on re-scrape.
        url = job_data.get("file_url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        try:
            result = supabase.table("job_updates").upsert(
                job_data,
                on_conflict="file_url"
            ).execute()
            if result.data:
                print(f"✅ [{job_data['category']}] {job_data['title'][:60]}")
                inserted += 1
        except Exception as e:
            print(f"❌ Supabase Error: {e}")

    return inserted


def scrape_page_data(url, page_name):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    print(f"\n🔄 {page_name} se data fetch ho raha hai...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"❌ Connection Fail: {response.status_code}")
            return 0
    except Exception as e:
        print(f"❌ Request Error: {e}")
        return 0

    soup = BeautifulSoup(response.text, 'html.parser')
    all_jobs = []

    # ── 1. Main Job Table (Current Recruitment) ──
    all_tables = [t for t in soup.find_all('table') if not t.find_parent('table')]
    seen_in_run = set()

    for job_table in all_tables:
        rows = job_table.find_all('tr', recursive=False) or job_table.find_all('tr')

        for row in rows:
            full_row_text = row.text.strip()
            link_tag = row.find('a')

            if not link_tag or not full_row_text:
                continue

            job_url = link_tag['href']
            if job_url.startswith('/'):
                job_url = f"https://www.majhinaukri.in{job_url}"

            title, last_date, vacancies = clean_and_split_data(full_row_text)

            if is_garbage(title):
                print(f"⏭️ Skipped: {title[:50]}")
                continue

            if any(x in job_url for x in ["/category/", "/contact-us/", "javascript:", "/share-", "/tag/"]):
                continue

            norm = normalize_title(title)
            if norm in seen_in_run:
                continue
            seen_in_run.add(norm)

            all_jobs.append({
                "title": title,
                "form_name": title,
                "vacancies": vacancies,
                "category": "Latest Jobs",
                "last_date": last_date,
                "eligibility": "See Details",
                "file_url": job_url,
                "status": "Active"
            })

    # ── 2. Hall Ticket Sidebar ──
    hall_tickets = scrape_sidebar_section(soup, "प्रवेशपत्र", "Hall Ticket")
    all_jobs.extend(hall_tickets)

    # ── 3. Results Sidebar ──
    results = scrape_sidebar_section(soup, "निकाल", "Result")
    all_jobs.extend(results)

    return upsert_jobs(all_jobs)


def run_production_scraper():
    home_count = scrape_page_data("https://www.majhinaukri.in/", "Homepage")
    rec_count = scrape_page_data("https://majhinaukri.in/current-recruitment/", "Current Recruitment Page")
    print(f"\n🚀 Naye records add hue: {home_count + rec_count}")

    delete_expired_jobs()


if __name__ == "__main__":
    run_production_scraper()