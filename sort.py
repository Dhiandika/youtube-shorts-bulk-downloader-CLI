import os
import glob
import re

def get_sorted_files(directory, ascending=True):
    files = glob.glob(os.path.join(directory, "*.mp4")) + glob.glob(os.path.join(directory, "*.webm"))
    files_with_mtime = [(f, os.path.getmtime(f)) for f in files]
    
    sorted_files = sorted(files_with_mtime, key=lambda x: x[1], reverse=not ascending)
    return [f[0] for f in sorted_files]

def clean_filename(name):
    # Hapus angka dan strip awal jika ada
    cleaned_name = re.sub(r'^\d+\s*-\s*', '', name)
    return cleaned_name

def rename_files(directory, ascending=True):
    sorted_files = get_sorted_files(directory, ascending)
    
    for index, file_path in enumerate(sorted_files, start=1):
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        ext = os.path.splitext(file_path)[1]
        
        # Bersihkan nama dari angka tambahan
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
    directory = input("Enter the directory containing videos: ").strip()
    order = input("Sort from oldest to newest? (y/n): ").strip().lower()
    ascending = order == 'y'
    
    if not os.path.exists(directory):
        print("Directory does not exist!")
        return
    
    rename_files(directory, ascending)
    print("Sorting and renaming completed!")

if __name__ == "__main__":
    main()