import os
import re
import hashlib
import logging
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)

LINKTREE_URL = "REDACTED_LINKTREE_URL"

def get_sunday_date():
    """Returns the date of the upcoming Sunday (or today if it is Sunday) in YYYY-MM-DD format."""
    today = datetime.now()
    days_ahead = 6 - today.weekday()  # Sunday is 6
    if days_ahead < 0: # Should not happen as 6 is max
        days_ahead += 7
    upcoming_sunday = today + timedelta(days=days_ahead)
    return upcoming_sunday.strftime("%Y-%m-%d")

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_linktree(url=LINKTREE_URL):
    """Fetches the Linktree page content."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def find_bulletin_link(html_content):
    """Parses HTML to find the 'Sunday Bulletin' link."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Linktree structure can vary, but usually links are in <a> tags.
    # We look for text containing "Sunday Bulletin"
    for a_tag in soup.find_all('a'):
        text = a_tag.get_text()
        if "Sunday Bulletin" in text:
            link = a_tag.get('href')
            return link
    return None

def get_file_checksum(content):
    """Calculates MD5 checksum of content."""
    return hashlib.md5(content).hexdigest()

def download_bulletin(url, cache_dir="bulletin_cache"):
    """
    Downloads the bulletin from the given URL.
    Handles Google Drive view links by converting to download links if possible,
    or using requests session for direct download.
    
    Returns the path to the downloaded file.
    """
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    # Convert Google Drive View link to Download link if necessary
    # Typical format: https://drive.google.com/file/d/FILE_ID/view?usp=sharing
    # Download format: https://drive.google.com/uc?export=download&id=FILE_ID
    file_id_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    download_url = url
    if file_id_match:
        file_id = file_id_match.group(1)
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    logger.info(f"Downloading from: {download_url}")

    try:
        response = requests.get(download_url, allow_redirects=True)
        response.raise_for_status()
        content = response.content
        
        # Try to get filename from Content-Disposition header
        content_disposition = response.headers.get('content-disposition')
        filename = None
        if content_disposition:
            fname_match = re.findall('filename="?([^"]+)"?', content_disposition)
            if fname_match:
                filename = fname_match[0]
        
        if not filename:
            # Fallback to generated name
            sunday_date = get_sunday_date()
            checksum = get_file_checksum(content)
            filename = f"bulletin_{sunday_date}_{checksum}.pdf"

        filepath = os.path.join(cache_dir, filename)

        # Check if file already exists
        if os.path.exists(filepath):
            logger.info(f"File already exists in cache: {filepath}")
            return filepath, filename

        # Save new file
        with open(filepath, 'wb') as f:
            f.write(content)
        
        logger.info(f"Downloaded and cached: {filepath}")
        return filepath, filename

    except Exception as e:
        logger.error(f"Failed to download bulletin: {e}")
        raise

def find_songbook_link(html_content):
    """Parses HTML to find the 'Songbook' link."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Look for text containing "Songbook"
    for a_tag in soup.find_all('a'):
        text = a_tag.get_text()
        if "Songbook" in text:
            link = a_tag.get('href')
            return link
    return None

def download_songbook(url, cache_dir="bulletin_cache"):
    """
    Downloads the songbook from the given URL.
    """
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    # Convert Google Drive View link to Download link if necessary
    file_id_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    download_url = url
    if file_id_match:
        file_id = file_id_match.group(1)
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    logger.info(f"Downloading songbook from: {download_url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }

    try:
        response = requests.get(download_url, headers=headers, allow_redirects=True)
        response.raise_for_status()
        content = response.content
        
        # Try to get filename from Content-Disposition header
        content_disposition = response.headers.get('content-disposition')
        filename = None
        if content_disposition:
            fname_match = re.findall('filename="?([^"]+)"?', content_disposition)
            if fname_match:
                filename = fname_match[0]
        
        if not filename:
            # Fallback to generated name
            checksum = get_file_checksum(content)
            filename = f"songbook_{checksum}.pdf"

        filepath = os.path.join(cache_dir, filename)

        # Check if file already exists
        if os.path.exists(filepath):
            logger.info(f"File already exists in cache: {filepath}")
            return filepath, filename

        # Save new file
        with open(filepath, 'wb') as f:
            f.write(content)
        
        logger.info(f"Downloaded and cached: {filepath}")
        return filepath, filename

    except Exception as e:
        logger.error(f"Failed to download songbook: {e}")
        raise
