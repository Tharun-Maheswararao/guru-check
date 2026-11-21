"""NPC portraits from Gemini image generation (gemini-nano-banana-2.1 through the Interactions API).

Every NPC is an invented character. The prompt forbids resembling any real person, so a portrait
is never the video's creator. Portraits are saved to data/portraits/<npc_id>.jpg and the record's
portrait_path points at it. If generation fails, the UI falls back to the pixel sprite.

    python -m backend.api.portrait            # add portraits to NPCs that don't have one
    python -m backend.api.portrait --force    # redraw every portrait
    python -m backend.api.portrait NPC_ID     # one NPC
"""

import argparse
import base64
import time
from pathlib import Path

from backend import llm
from backend.config import DATA_DIR, IMAGE

COLORS = {"gold": "golden yellow", "green": "bright green", "red": "hot pink red", "cyan": "electric cyan",
          "violet": "violet purple"}
MOODS = {
    "Real Edge": "calm, confident, quietly proud",
    "Lucky": "smug but secretly nervous, sweating a little",
    "Just the Market": "ordinary and slightly sheepish",
    "Untestable": "mysterious, half hidden in fog, shrugging",
}


def portrait_prompt(record: dict) -> str:
    color = COLORS.get(record.get("color", ""), "golden yellow")
    mood = MOODS.get(record.get("verdict", ""), "curious")
    personality = " ".join(str(record.get("personality", "")).split())[:300]
    return (
        f"16-bit pixel art head-and-shoulders portrait of {record.get('name', 'a trader')}, an invented "
        f"trader character in a retro arcade game. Archetype: {record.get('archetype', 'trader')}. "
        f"Personality: {personality}. Expression: {mood}. Main accent color {color} in the clothing. "
        "Dark navy night city background with a few stars. Centered, facing the viewer, crisp pixels. "
        "This is a fictional person: do not resemble any real person, YouTuber, influencer or celebrity. "
        "No text, letters, numbers, logos or watermarks."
    )


def generate_portrait(record: dict, out_dir: Path | None = None) -> str:
    """Draw a portrait for an NPC record and return its file path."""
    out_dir = Path(out_dir or DATA_DIR / "portraits")
    prompt = portrait_prompt(record)

    def call() -> bytes:
        start = time.time()
        interaction = llm._client(IMAGE).interactions.create(
            model=IMAGE.model, store=False, response_modalities=["image"],
            response_format={"type": "image", "aspect_ratio": "1:1", "image_size": "512", "mime_type": "image/jpeg"},
            input=[{"type": "text", "text": prompt}],
        )
        image = interaction.output_image
        if image is None or not image.data:
            raise RuntimeError("Image model returned no image")
        data = base64.b64decode(image.data) if isinstance(image.data, str) else image.data
        llm._record("portrait", IMAGE.model, prompt, f"{len(data)} bytes", time.time() - start)
        return data

    data = llm._retry(call, attempts=3)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{record['npc_id']}.jpg"
    path.write_bytes(data)
    return str(path)


def main() -> None:
    from backend.npc_store import store

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("npc_id", nargs="?")
    parser.add_argument("--force", action="store_true", help="redraw portraits that already exist")
    args = parser.parse_args()
    records = [store.get_npc(args.npc_id)] if args.npc_id else store.list_npcs()
    for rec in records:
        if rec is None:
            raise SystemExit(f"No NPC {args.npc_id}")
        if rec.get("portrait_path") and Path(rec["portrait_path"]).is_file() and not args.force:
            continue
        rec["portrait_path"] = generate_portrait(rec)
        store.save_npc(rec)
        print(f"{rec['npc_id']}: {rec['portrait_path']}")


if __name__ == "__main__":
    main()
