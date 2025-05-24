<div align='center'>

<h1>Download all YouTube Shorts from a channel. Bulk download all shorts from a specified YouTube channel using Python 3.10.0 and above  </h1>
<h4>


</div>

# :notebook_with_decorative_cover: Table of Contents

- [About the Project](#star2-about-the-project)
  - [Core Functionality: YouTube Shorts Bulk Downloader](#electric_plug-core-functionality-youtube-shorts-bulk-downloader)
  - [Additional Utility Scripts](#wrench-additional-utility-scripts)
    - [Automated Caption Generation (`caption.py`)](#performing_arts-automated-caption-generation-captionpy)
    - [File Sorting and Renaming (`sort.py`)](#floppy_disk-file-sorting-and-renaming-sortpy)
- [Screenshots](#camera-screenshots)
- [Getting Started](#toolbox-getting-started)
- [Contributing](#wave-contributing)


## :star2: About the Project
---
This project provides a command-line interface (CLI) to bulk download all YouTube Shorts from a specified YouTube channel. It's built using Python 3.10.0 and above.

### :electric_plug: Core Functionality: YouTube Shorts Bulk Downloader (`main.py`)
The main script (`main.py`) of this project is designed to:
- Fetch a list of Shorts videos from a given YouTube channel.
- Support limiting the number of videos to be fetched.
- Download Shorts videos with selectable quality options.
- Save files with names based on the video title and sequential numbering.
- Save video captions (descriptions) into text files.
- Utilize multithreading to speed up the download process.
- Implement automatic retries in case of failures.
- Display download progress using `tqdm`.
- Detect and remove duplicate files to prevent redundant storage.
- Show a summary of the download results.

---
### :wrench: Additional Utility Scripts

This project also includes a couple of utility scripts to help manage and enhance the downloaded content:

#### :performing_arts: Automated Caption Generation (`caption.py`)

The `caption.py` script is designed to automatically generate engaging captions for social media content, particularly focusing on Hololive talents. Its key capabilities include:

- **Flexible Input**: Reads all `.txt` files stored in the `downloads_cut` folder. Each text file serves as the basis for generating a caption.
- **Gemini AI Integration**: Uses Google's generative AI model (Gemini Pro) to create caption narratives. Users will be prompted to enter their Gemini API key directly in the terminal when the script is run.
- **Gemini API Key**: The API key required to run this script can be obtained for free from [Google AI Studio](https://aistudio.google.com/app/apikey).
- **Structured Prompting**: Sends a detailed system prompt and a one-shot example to the AI model to ensure the generated captions adhere to the desired format, including:
    - A brief description of the talent.
    - Interesting facts or unique details about the talent.
    - Mention of the clip's source (if relevant from the input prompt).
    - A collection of 15-25 relevant hashtags.
- **Direct Output**: Once a caption is successfully generated, the script will **overwrite** the original `.txt` file's content with the new caption. This means the initial prompt content in that file will be replaced by the AI-processed caption.
- **Usage**: Simply run `python caption.py` from the terminal, enter your Gemini API key when prompted, and the script will process all text files in the `downloads_cut` folder.

**Important**: Since this script overwrites the original files, it's advisable to back up the files in `downloads_cut` if you wish to preserve the initial prompt content.

---

#### :floppy_disk: File Sorting and Renaming (`sort.py`)

The `sort.py` script is a utility for managing and tidying up your video collection, especially those downloaded in bulk. Here are its main functions:

- **Flexible Sorting**: Videos (formats `.mp4` and `.webm`) in the specified directory will be sorted by their modification time. By default, sorting is from oldest to newest. The `--desc` option can be used to sort from newest to oldest.
- **Automatic Renaming**: After sorting, video files will be renamed following the format `XX - CleanedFileName.extension` (e.g., `01 - My Cool Video.mp4`).
- **Filename Cleaning**: Before new numbering is applied, the script cleans the original filenames by removing any leading numbers and hyphens (e.g., `123 - Original Video.mp4` becomes `Original Video.mp4`).
- **Handling of Associated Text Files**: If `.txt` files exist with the same base name as the video files (e.g., caption or metadata files), these text files will also be renamed to match the new video filenames (e.g., `01 - My Cool Video.txt`).
- **Interactive Directory Input**: If the directory path is not included as an argument when running the script, the user will be prompted to enter the directory path interactively via the terminal.

**How to Use `sort.py`**:

1.  **Running with a Directory Path**:
    ```bash
    python sort.py "path/to/your/video_folder"
    ```
    Replace `"path/to/your/video_folder"` with the actual path to the directory containing your videos.

2.  **Running with Reverse Sorting (Newest to Oldest)**:
    ```bash
    python sort.py "path/to/your/video_folder" --desc
    ```

3.  **Running Interactively (Will Prompt for Directory Input)**:
    ```bash
    python sort.py
    ```
    The script will ask you to enter the directory path.

**Description**:
This script is very useful for organizing video files by renaming them based on their modification time order. This simplifies the management of video collections, especially for content downloaded in large quantities. Its ability to also rename associated text files ensures that metadata or captions remain synchronized with their corresponding video files.
---

## :camera: Screenshots
<div align="center"> <a href=""><img src="/images/1.png" alt='image' width='800'/></a> </div>
<div align="center"> <a href=""><img src="/images/image.png" alt='image' width='800'/></a> </div>

## :toolbox: Getting Started

### :gear: Installation

- Install dependencies:
```bash
pip install -r requirements.txt
```
- Run the main downloader script:
```bash
python main.py
```

For details on the utility scripts (`caption.py`, `sort.py`), please refer to their respective sections in "Additional Utility Scripts".

---
## :wave: Contributing

