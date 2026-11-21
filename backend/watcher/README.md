# Watcher (Person 1)

**Model:** Gemini 4 Hydrogen, called through the regular Gemini API with the YouTube URL.
Never download the video, since that breaks YouTube's terms.

**Input:** a YouTube URL.
**Output:** timestamped segments, which are the handoff to the Scanner.

Draft format, to be locked by 11:30:

```json
{
  "video": {
    "url": "https://www.youtube.com/watch?v=...",
    "title": "",
    "upload_date": "2026-05-02",
    "duration_s": 0
  },
  "segments": [
    {
      "segment_id": 0,
      "start_s": 0.0,
      "end_s": 12.5,
      "speech": "what the creator says in this span",
      "on_screen": "chart drawings, indicator settings, text overlays"
    }
  ]
}
```
