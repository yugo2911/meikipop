import json
import re
import os
import glob

# Set folder where the term_bank files are located
INPUT_FOLDER = r"C:\Users\rias\Documents\Projects\Github Desktop\meikipop\data\Dicitoanry Convert\PixivLight\PixivLight_2025-11-02"
os.makedirs(os.path.join(INPUT_FOLDER, "converted"), exist_ok=True)
OUTPUT_FILE = os.path.join(INPUT_FOLDER, "converted", "PixivLight_JMdict.json")

def has_kanji(text):
    return any('\u4e00' <= ch <= '\u9fff' for ch in text)

def extract_gloss(entry):
    glosses = []
    try:
        for block in entry[5]:
            if block.get("type") == "structured-content":
                for item in block.get("content", []):
                    if item.get("tag") == "ul":
                        for li in item.get("content", []):
                            text = li.get("content")
                            if isinstance(text, str):
                                cleaned = text.strip()
                                if cleaned:
                                    parts = re.split(r'[。！？!?]+', cleaned)
                                    for part in parts:
                                        part = part.strip()
                                        if part:
                                            glosses.append(part + "。")
        return glosses
    except:
        return []


jm_entries = []

print("🔍 Searching for term_bank files in:", INPUT_FOLDER)
print("📁 Files in INPUT_FOLDER:", os.listdir(INPUT_FOLDER))

# Find all term_bank_*.json files
for file in sorted(glob.glob(os.path.join(INPUT_FOLDER, "term_bank_*.json"))):
    print("📌 Processing:", os.path.basename(file))
    
    with open(file, "r", encoding="utf-8") as f:
        pixiv = json.load(f)

    # Convert entries from each file
    for item in pixiv:
        label = item[0]
        read = item[1]
        seq = item[4]

        gloss = extract_gloss(item)
        if not gloss:  # Filter B
            continue

        entry = {
            "seq": seq,
            "r_ele": [{"reb": read}],
            "sense": [{"gloss": gloss}]
        }

        if has_kanji(label):
            entry["k_ele"] = [{"keb": label}]

        jm_entries.append(entry)

# Save combined result
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(jm_entries, f, ensure_ascii=False, indent=2)

print("\n✅ Conversion Complete!")
print("✅ Total Entries Saved:", len(jm_entries))
print("📄 Output File:", OUTPUT_FILE)