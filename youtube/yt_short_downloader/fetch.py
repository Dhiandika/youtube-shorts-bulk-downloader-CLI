import traceback
import yt_dlp

__all__ = ["get_short_links"]


def get_short_links(channel_url: str, max_videos: int | None = None):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'playlistend': max_videos if max_videos else None,
    }
    try:
        if '/@' in channel_url:
            channel_username = channel_url.split('/@')[1].split('/')[0]
            channel_url = f'https://www.youtube.com/@{channel_username}/shorts'
        else:
            channel_url = channel_url.split('/about')[0] + '/shorts'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(channel_url, download=False)

        if 'entries' in result:
            video_entries = result['entries'][:max_videos] if max_videos else result['entries']
            channel_name = result.get('uploader', channel_url.split('/@')[-1])
            video_entries = sorted(video_entries, key=lambda v: v.get('upload_date', '00000000'), reverse=True)
            return video_entries, channel_name
        else:
            print("Tidak ada video ditemukan di channel ini.")
            return [], ""
    except Exception as e:
        tb = traceback.format_exc()
        print(f"Error fetching video list: {e}")
        with open("download_errors.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"Error fetching video list from {channel_url}:\n{tb}\n")
        return [], ""