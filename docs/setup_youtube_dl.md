# Youtube-dl

## Install

```bash
  sudo apt update
  sudo apt install python3-pip
  pip3 install --upgrade youtube_dl
  sudo apt install ffmpeg atomicparsley
```

## Use

```bash
youtube-dl --restrict-filename -i -w --no-post-overwrites -o "%(title)s.%(ext)s" --add-metadata LINK
```

```bash
-a  # for a txt file of links, one per line
--simulate  # for test
--add-metadata
--extract-audio --embed-thumbnail --audio-format "best"  # to keep only audio
```

```bash
# cd to the folder you want to download to
uv init
uv add yt-dlp
uv run yt-dlp -f best -o "%(playlist_index)s - %(title)s.%(ext)s" "https://youtube.com/playlist?list=PLNQpggnSpD4oj3PCsZTzbzLFjHmOxTRHr&si=Q_A9GqpffYmiYYrL"
```
