# Watcher (Person 1)

**Model:** Gemini 4 Hydrogen (`gemini-4-hydrogen`) through the Interactions API, with the YouTube
URL as a `{"type": "video", "uri": ...}` input block and a JSON schema for the output. Never
download the video, since that breaks YouTube's terms. Videos must be public.

**Input:** a YouTube URL in any common form (watch, youtu.be, shorts).
**Output** (`watch()` in `watcher.py`): timestamped segments, which are the handoff to the Scanner.

```json
{
  "video": {
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "video_id": "VIDEO_ID",
    "title": "from YouTube oEmbed",
    "upload_date": "",
    "duration_s": 612.0,
    "language": "en",
    "music_over_speech": false
  },
  "segments": [
    {
      "segment_id": 0,
      "start_s": 0.0,
      "end_s": 12.5,
      "speech": "what the creator says in this span, in English",
      "on_screen": "chart symbol and timeframe, indicator settings, drawings, text overlays"
    }
  ]
}
```

Segments are 10 to 30 seconds, sorted, numbered from 0, and empty ones are dropped. Times are in
seconds; `"4:12"` style answers from the model are converted. `upload_date` is blank because oEmbed
doesn't give it.
