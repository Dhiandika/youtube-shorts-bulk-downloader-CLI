import os
import glob
import re
import argparse

def get_sorted_files(directory, ascending=True):
    files = glob.glob(os.path.join(directory, "*.mp4")) + glob.glob(os.path.join(directory, "*.webm"))
    files_with_mtime = [(f, os.path.getmtime(f)) for f in files]
    
    sorted_files = sorted(files_with_mtime, key=lambda x: x[1], reverse=not ascending)
    return [f[0] for f in sorted_files]

def clean_filename(name):
    return re.sub(r'^\d+\s*-\s*', '', name)  # Hapus angka dan strip awal jika ada

def rename_files(directory, ascending=True):
    sorted_files = get_sorted_files(directory, ascending)
    
    for index, file_path in enumerate(sorted_files, start=1):
        base_name, ext = os.path.splitext(os.path.basename(file_path))
        
        new_base_name = clean_filename(base_name)
        new_name = f"{index:02d} - {new_base_name}{ext}"
        new_path = os.path.join(directory, new_name)
        
        txt_file_old = os.path.join(directory, f"{base_name}.txt")
        txt_file_new = os.path.join(directory, f"{index:02d} - {new_base_name}.txt")
        
        os.rename(file_path, new_path)
        print(f"Renamed: {file_path} -> {new_path}")
        
        if os.path.exists(txt_file_old):
            os.rename(txt_file_old, txt_file_new)
            print(f"Renamed: {txt_file_old} -> {txt_file_new}")

def main():
    parser = argparse.ArgumentParser(description="Sort and rename video files in a directory.")
    parser.add_argument("directory", nargs="?", help="Path to the directory containing videos")
    parser.add_argument("--desc", action="store_true", help="Sort from newest to oldest (default is oldest to newest)")
    
    args = parser.parse_args()
    
    if not args.directory:
        args.directory = input("Enter the directory containing videos: ").strip()
    
    ascending = not args.desc
    
    if not os.path.exists(args.directory):
        print("Error: Directory does not exist!")
        print("Hint: Make sure the directory path is correct and accessible.")
        return
    
    rename_files(args.directory, ascending)
    print("Sorting and renaming completed!")
    print("Hint: Use --desc if you want to sort from newest to oldest.")

if __name__ == "__main__":
    main()
