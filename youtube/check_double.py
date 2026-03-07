import os

def normalize_url(url):
    """Normalize URL by removing trailing slash and whitespace."""
    return url.strip().rstrip('/')

def check_duplicates(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    original_links = [line.strip() for line in lines if line.strip()]
    seen = set()
    duplicates = {}
    unique_links = []

    for link in original_links:
        norm_link = normalize_url(link)
        if norm_link in seen:
            duplicates[norm_link] = duplicates.get(norm_link, 1) + 1
        else:
            seen.add(norm_link)
            unique_links.append(link)

    print(f"\nTotal links found: {len(original_links)}")
    
    if not duplicates:
        print("No duplicate links found.")
        return

    print(f"Found {len(duplicates)} duplicate(s):")
    for link, count in duplicates.items():
        print(f"- {link} (found {count} times)")

    choice = input("\nDo you want to remove duplicates? (y/n): ").strip().lower()
    if choice == 'y':
        with open(file_path, 'w', encoding='utf-8') as f:
            for link in unique_links:
                f.write(link + '\n')
        print(f"Duplicates removed. Saved {len(unique_links)} unique links to {file_path}")
    else:
        print("No changes made.")

if __name__ == "__main__":
    file_path = os.path.join(os.path.dirname(__file__), 'short_link.txt')
    check_duplicates(file_path)
