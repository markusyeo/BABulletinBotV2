import logging
import sys
import os

# Add the parent directory to sys.path to allow importing from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.bulletin import fetch_linktree, find_bulletin_link, download_bulletin

logging.basicConfig(level=logging.INFO)

def main():
    print("Fetching Linktree...")
    try:
        html = fetch_linktree()
        print("Linktree fetched successfully.")
        
        print("Finding Bulletin link...")
        link = find_bulletin_link(html)
        
        if link:
            print(f"Found link: {link}")
            print("Downloading bulletin...")
            filepath, filename = download_bulletin(link)
            print(f"Bulletin downloaded to: {filepath}")
            print(f"Filename: {filename}")
        else:
            print("Sunday Bulletin link not found.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
