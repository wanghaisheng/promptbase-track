import os
import csv
import sys
from datetime import datetime
import requests
import re
# sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))
from parse_url_from_sitemap import collect_all_url_details_from_sitemap

def read_domains(domain_file):
    with open(domain_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_sitemap_url(domain):
    if domain.startswith('http://') or domain.startswith('https://'):
        base = domain
    else:
        base = 'https://' + domain
    return base.rstrip('/') + '/sitemap.xml'

def check_url_200(url):
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False

def get_robots_sitemaps(domain, prioritized_patterns=None):
    if domain.startswith('http://') or domain.startswith('https://'):
        base = domain
    else:
        base = 'https://' + domain
    robots_url = base.rstrip('/') + '/robots.txt'
    try:
        resp = requests.get(robots_url, timeout=10)
        if resp.status_code == 200:
            sitemaps = re.findall(r'^Sitemap:\s*(\S+)', resp.text, re.MULTILINE | re.IGNORECASE)
            if not sitemaps:
                return []
            if prioritized_patterns:
                prioritized = []
                others = []
                for s in sitemaps:
                    if any(pattern in s for pattern in prioritized_patterns):
                        prioritized.append(s)
                    else:
                        others.append(s)
                return prioritized + others
            else:
                return sitemaps
    except Exception:
        pass
    return []

def aggregate_all_domains(domain_file, output_file):
    domains = read_domains(domain_file)
    all_url_details = []
    today = datetime.now().strftime('%Y-%m-%d')
    date_folder = f"results_{today}"
    if not os.path.exists(date_folder):
        os.makedirs(date_folder)
    progress_file = os.path.join(date_folder, f'domain_progress_{today}.txt')
    failed_file = os.path.join(date_folder, f'failed_domains_{today}.txt')
    # 读取已处理进度
    processed_domains = set()
    if os.path.exists(progress_file):
        with open(progress_file, 'r', encoding='utf-8') as pf:
            processed_domains = set([line.strip() for line in pf if line.strip()])
    failed_domains = set()
    if os.path.exists(failed_file):
        with open(failed_file, 'r', encoding='utf-8') as ff:
            failed_domains = set([line.strip() for line in ff if line.strip()])
    for domain in domains:
        if domain in processed_domains:
            print(f"Skipping already processed domain: {domain}")
            continue
        
        print(f"\nProcessing domain: {domain}")
        sitemap_urls_to_try = []
        
        # Construct base_url for the current domain
        current_base_url = domain
        if not (current_base_url.startswith('http://') or current_base_url.startswith('https://')):
            current_base_url = 'https://' + current_base_url
        current_base_url = current_base_url.rstrip('/')

        # Attempt 1: Get from robots.txt
        print(f"  Checking robots.txt for sitemaps...")
        # Pass domain to get_robots_sitemaps, it handles base URL construction internally
        robots_sitemaps = get_robots_sitemaps(domain, prioritized_patterns=["promptbase.com/sitemap-master-index.xml"])
        if robots_sitemaps:
            for s_url in robots_sitemaps:
                if s_url not in sitemap_urls_to_try: # Ensure uniqueness
                    sitemap_urls_to_try.append(s_url)
            print(f"  Found in robots.txt: {sitemap_urls_to_try}")

        # Attempt 2: Try default /sitemap.xml if not already found via robots.txt
        default_sitemap_url = current_base_url + '/sitemap.xml' 
        if default_sitemap_url not in sitemap_urls_to_try:
            print(f"  Checking default sitemap: {default_sitemap_url}...")
            if check_url_200(default_sitemap_url):
                sitemap_urls_to_try.append(default_sitemap_url)
                print(f"  Found default sitemap: {default_sitemap_url}")
        
        # Attempt 3: Try other common sitemap names if no sitemaps found from robots.txt or default
        if not sitemap_urls_to_try:
            print(f"  No sitemaps found via robots.txt or default /sitemap.xml. Trying common alternatives...")
            COMMON_SITEMAP_FILENAMES = [
                "sitemap_index.xml", "sitemap.xml.gz", "sitemap_index.xml.gz",
                "sitemap.php", "sitemap.txt",
                "post-sitemap.xml", "page-sitemap.xml", "category-sitemap.xml", "product-sitemap.xml",
                "sitemapindex.xml", "sitemap.gz", "sitemapindex.xml.gz",
                "sitemap/index.xml", "sitemaps.xml", "sitemap.ashx"
            ]
            for sitemap_file in COMMON_SITEMAP_FILENAMES:
                alternative_sitemap_url = f"{current_base_url}/{sitemap_file}"
                print(f"  Checking alternative: {alternative_sitemap_url}...")
                if check_url_200(alternative_sitemap_url):
                    sitemap_urls_to_try.append(alternative_sitemap_url)
                    print(f"  Found alternative sitemap: {alternative_sitemap_url}")
                    break # Found one common alternative, proceed with it

        if not sitemap_urls_to_try:
            print(f"  No sitemap found after all checks for {domain}")
            failed_domains.add(domain)
            with open(failed_file, 'a', encoding='utf-8') as ff:
                ff.write(domain + '\n')
            with open(progress_file, 'a', encoding='utf-8') as pf:
                pf.write(domain + '\n')
            continue
            
        print(f"  Potential sitemap URLs to try for {domain}: {sitemap_urls_to_try}")
        success = False
        for sitemap_url_to_process in sitemap_urls_to_try:
            print(f'Processing {sitemap_url_to_process}')
            try:
                url_details = collect_all_url_details_from_sitemap(sitemap_url_to_process, today=today)
                for d in url_details:
                    d['domain'] = domain
                all_url_details.extend(url_details)
                success = True
                break  # Only process the first working sitemap
            except Exception as e:
                print(f'Failed to process {sitemap_url_to_process}: {e}')
        if not success:
            failed_domains.add(domain)
            with open(failed_file, 'a', encoding='utf-8') as ff:
                ff.write(domain + '\n')
        with open(progress_file, 'a', encoding='utf-8') as pf:
            pf.write(domain + '\n')
    # Save all results
    if all_url_details:
        fieldnames = [
            # 'domain', 
            'loc', 'lastmodified', 'added_date']
        output_file_with_date_base = os.path.join(date_folder, f'all_domains_url_details_{today}')
        max_size = 90 * 1024 * 1024  # 90MB
        file_index = 1
        output_file_with_date = f"{output_file_with_date_base}_part{file_index}.csv"
        f = open(output_file_with_date, 'w', encoding='utf-8', newline='')
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        current_size = f.tell()
        for i, d in enumerate(all_url_details):
            writer.writerow(d)
            # 检查文件大小，超过90M则切换新文件
            if f.tell() >= max_size:
                f.close()
                file_index += 1
                output_file_with_date = f"{output_file_with_date_base}_part{file_index}.csv"
                f = open(output_file_with_date, 'w', encoding='utf-8', newline='')
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
        f.close()
        print(f"Aggregated {len(all_url_details)} URLs from {len(domains)} domains. Saved to {output_file_with_date_base}_part*.csv")
    else:
        print("No URLs found.")

def main():
    domain_file = 'domainlist.csv'
    today = datetime.now().strftime('%Y-%m-%d')
    date_folder = f"results_{today}"
    if not os.path.exists(date_folder):
        os.makedirs(date_folder)
    output_file = os.path.join(date_folder, f'all_domains_url_details_{today}.csv')
    aggregate_all_domains(domain_file, output_file)

if __name__ == '__main__':
    main()

