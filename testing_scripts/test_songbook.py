import logging
import sys
import os

# Add the parent directory to sys.path to allow importing from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.bulletin import fetch_linktree, find_songbook_link, download_songbook

logging.basicConfig(level=logging.INFO)

def main():
    print("Fetching Linktree...")
    try:
        html = fetch_linktree()
        print("Linktree fetched successfully.")
        
        print("Finding Songbook link...")
        link = find_songbook_link(html)
        
        if link:
            print(f"Found link: {link}")
            print("Downloading songbook...")
            filepath, filename = download_songbook(link)
            print(f"Songbook downloaded to: {filepath}")
            print(f"Filename: {filename}")
        else:
            print("Songbook link not found.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
