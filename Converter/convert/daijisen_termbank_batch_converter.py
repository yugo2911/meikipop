#!/usr/bin/env python3
"""
Daijisen Term Bank to JMDict Batch Converter
Enhanced with filtering for proper nouns, media titles, and excessive definitions
"""

import json
import os
import re
from pathlib import Path


def extract_all_text(elem, skip_tags=None):
    """Extract all text from element"""
    if elem is None:
        return ''
    
    if isinstance(elem, str):
        return elem
    
    if isinstance(elem, list):
        return ''.join(extract_all_text(item, skip_tags) for item in elem)
    
    if isinstance(elem, dict):
        if elem.get('tag') == 'img':
            return ''
        
        if skip_tags and elem.get('tag') in skip_tags:
            return ''
        
        if 'content' in elem:
            return extract_all_text(elem['content'], skip_tags)
    
    return ''


def is_proper_noun_entry(text):
    """Check if entry is primarily a proper noun (place, person, title)"""
    if not text:
        return False
    
    # Check for place name patterns
    place_patterns = [
        r'市の区名',
        r'区の.*の区名',
        r'市の地名',
        r'都の.*区',
        r'県の.*市',
        r'の旧地名',
        r'^アクセント\s+[ぁ-ん]+\s+\d+',  # Just accent info
    ]
    
    for pattern in place_patterns:
        if re.search(pattern, text):
            return True
    
    # Check if it's mostly a list of place names
    place_markers = ['市の', '区の', '県の', '町の', '村の']
    if sum(1 for m in place_markers if m in text) >= 2:
        return True
    
    return False


def is_media_title_entry(text):
    """Check if entry is primarily a media title"""
    if not text:
        return False
    
    # Patterns indicating media titles
    media_patterns = [
        r'のテレビドラマ',
        r'の日本映画',
        r'の米国映画',
        r'のアメリカ映画',
        r'テレビ.*系列',
        r'TBS.*放映',
        r'フジテレビ.*制作',
        r'\d{4}年.*公開',
        r'\d{4}年\d+月～',
        r'監督.*主演',
        r'出演.*脚本',
    ]
    
    for pattern in media_patterns:
        if re.search(pattern, text):
            return True
    
    return False


def should_skip_sense(text):
    """Check if a specific sense should be skipped"""
    if not text or len(text) < 10:
        return True
    
    # Skip if it's just a city/region name
    if re.match(r'^[ぁ-ん\u4e00-\u9faf]+[市区町村県]の[ぁ-ん\u4e00-\u9faf]+。?$', text):
        return True
    
    # Skip if it's media production details
    if re.search(r'(監督|主演|出演|脚本|制作|放映|公開)[：:.]', text):
        return True
    
    # Skip if it's just a year and title
    if re.match(r'^\d{4}年', text) and len(text) < 30:
        return True
    
    return False


def clean_definition(text):
    """Clean and filter definition text"""
    if not text:
        return ''
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Remove references
    text = re.sub(r'[（(《]→[^)）》]+[)）》]', '', text)
    
    # Remove source citations
    text = re.sub(r'〈[^〉]+〉', '', text)
    
    # Remove production details
    text = re.sub(r'[。、]\s*(監督|主演|出演|脚本|制作|放映|公開)[：:.].*?(?=[。、]|$)', '', text)
    
    # Remove year ranges in media
    text = re.sub(r'\d{4}年\d+月～\d{4}年\d+月', '', text)
    
    # Keep only first 2 quoted examples
    quotes = re.findall(r'「[^」]+」', text)
    if len(quotes) > 2:
        for quote in quotes[2:]:
            text = text.replace(quote, '')
    
    # Remove long parentheticals
    text = re.sub(r'[（(][^)）]{40,}[)）]', '', text)
    
    # Remove cross-references
    text = re.sub(r'[⇔↔][^\s。、]+', '', text)
    
    # Clean up spacing
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Limit length
    MAX_LENGTH = 180
    if len(text) > MAX_LENGTH:
        cut = text[:MAX_LENGTH].rfind('。')
        if cut > 100:
            text = text[:cut + 1]
        else:
            cut = text[:MAX_LENGTH].rfind('、')
            if cut > 100:
                text = text[:cut + 1]
            else:
                text = text[:MAX_LENGTH] + '...'
    
    return text.strip()


def extract_core_definition(text):
    """Extract core definition, removing supplementary material"""
    if not text:
        return ''
    
    # Stop before supplementary markers
    for marker in ['。「', '。《', '。〔']:
        if marker in text:
            parts = text.split(marker, 1)
            if len(parts[0]) > 20:
                text = parts[0] + '。'
                break
    
    # Remove cascading examples
    quote_pattern = r'(「[^」]{0,50}」.*?)「[^」]+」「[^」]+」'
    text = re.sub(quote_pattern, r'\1', text)
    
    return text


def split_into_senses(text):
    """Split text by numbered markers, with limit"""
    if not text:
        return []
    
    # Split by markers
    parts = re.split(r'([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|㋐|㋑|㋒|㋓|㋔)', text)
    
    senses = []
    current = ''
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        if re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㋐㋑㋒㋓㋔]$', part):
            if current.strip():
                core = extract_core_definition(current)
                cleaned = clean_definition(core)
                
                # Skip if it should be filtered
                if cleaned and len(cleaned) > 10 and not should_skip_sense(cleaned):
                    senses.append(cleaned)
            current = ''
        else:
            current += part
    
    # Add last sense
    if current.strip():
        core = extract_core_definition(current)
        cleaned = clean_definition(core)
        if cleaned and len(cleaned) > 10 and not should_skip_sense(cleaned):
            senses.append(cleaned)
    
    # If no splits or all filtered out
    if not senses:
        core = extract_core_definition(text)
        cleaned = clean_definition(core)
        if cleaned and len(cleaned) > 10 and not should_skip_sense(cleaned):
            return [cleaned]
        return []
    
    # Limit to 3 most important senses for clarity
    MAX_SENSES = 3
    return senses[:MAX_SENSES]


def extract_definitions(structured_content):
    """Extract definitions with filtering"""
    if not structured_content or not isinstance(structured_content, list):
        return []
    
    skip_tags = {'img'}
    all_text = ''
    
    for item in structured_content:
        if not isinstance(item, dict):
            continue
        
        if item.get('type') == 'structured-content':
            text = extract_all_text(item.get('content', []), skip_tags)
            if text:
                all_text += text + ' '
    
    all_text = all_text.strip()
    
    if not all_text:
        return []
    
    # Check if should skip entire entry
    if is_proper_noun_entry(all_text):
        return []
    
    if is_media_title_entry(all_text):
        return []
    
    # Filter out headword section
    def_start = all_text.find('】')
    if def_start != -1:
        all_text = all_text[def_start + 1:].strip()
    
    # Remove accent marks
    all_text = re.sub(r'[⓪①②③④⑤⑥⑦⑧⑨](?=\s|$)', '', all_text)
    
    # Remove kanji notation blocks
    all_text = re.sub(r'^【[^】]+】\s*', '', all_text)
    
    # Remove counter information
    all_text = re.sub(r'^[一二三四五六七八九十]+本。?', '', all_text)
    
    # Check if numbered senses exist
    if re.search(r'[①②③④⑤⑥⑦⑧⑨⑩]', all_text):
        return split_into_senses(all_text)
    
    # No numbered senses - extract first core definition
    sentences = []
    for sent in all_text.split('。')[:2]:
        sent = sent.strip()
        if len(sent) > 15:
            core = extract_core_definition(sent + '。')
            cleaned = clean_definition(core)
            if cleaned and len(cleaned) > 10 and not should_skip_sense(cleaned):
                sentences.append(cleaned)
    
    if sentences:
        return sentences[:1]
    
    # Fallback
    core = extract_core_definition(all_text)
    cleaned = clean_definition(core)
    if cleaned and len(cleaned) > 10 and not should_skip_sense(cleaned):
        return [cleaned]
    
    return []


def extract_reading(structured_content, fallback_reading):
    """Extract reading from structured content"""
    if not structured_content or not isinstance(structured_content, list):
        return fallback_reading
    
    for item in structured_content:
        if not isinstance(item, dict):
            continue
        
        if item.get('type') != 'structured-content':
            continue
        
        def find_reading(elem):
            if not isinstance(elem, dict):
                return None
            
            name = elem.get('data', {}).get('name', '')
            if name == '見出仮名':
                text = extract_all_text(elem.get('content'))
                if text:
                    text = text.replace(' ', '').replace('　', '')
                    text = re.sub(r'[⓪①②③④⑤⑥⑦⑧⑨]', '', text)
                    text = text.replace('【', '').replace('】', '')
                    return text.strip()
            
            if 'content' in elem:
                content = elem['content']
                if isinstance(content, list):
                    for child in content:
                        result = find_reading(child)
                        if result:
                            return result
                else:
                    return find_reading(content)
            
            return None
        
        result = find_reading(item)
        if result:
            return result
    
    return fallback_reading


def extract_pos(structured_content):
    """Extract part of speech"""
    if not structured_content or not isinstance(structured_content, list):
        return []
    
    pos_list = []
    
    for item in structured_content:
        if not isinstance(item, dict):
            continue
        
        if item.get('type') != 'structured-content':
            continue
        
        def find_pos(elem):
            if not isinstance(elem, dict):
                return
            
            name = elem.get('data', {}).get('name', '')
            
            if name in ['品詞', 'hinshi', 'FM', '品詞G']:
                text = extract_all_text(elem.get('content'))
                if text and text.strip():
                    cleaned = text.strip().replace('〘', '').replace('〙', '').strip()
                    if cleaned and cleaned not in pos_list:
                        pos_list.append(cleaned)
                return
            
            if 'content' in elem:
                content = elem['content']
                if isinstance(content, list):
                    for child in content:
                        find_pos(child)
                else:
                    find_pos(content)
        
        find_pos(item)
    
    return pos_list


def has_kanji(text):
    """Check if text contains kanji"""
    if not text:
        return False
    return bool(re.search(r'[\u4e00-\u9faf]', text))


def convert_entry(entry, index, base_seq):
    """Convert single entry"""
    try:
        term = entry[0] if len(entry) > 0 else ''
        reading = entry[1] if len(entry) > 1 else ''
        def_tags = entry[2] if len(entry) > 2 else ''
        rules = entry[3] if len(entry) > 3 else ''
        score = entry[4] if len(entry) > 4 else 0
        definitions = entry[5] if len(entry) > 5 else []
        seq = entry[6] if len(entry) > 6 else None
        
        # Get reading
        reading = extract_reading(definitions, reading)
        if reading:
            reading = reading.replace(' ', '')
        
        # Get definitions (with filtering)
        glosses = extract_definitions(definitions)
        
        if not glosses or not any(g for g in glosses):
            return None, False
        
        # Get POS
        pos_array = extract_pos(definitions)
        
        # Build entry
        entry_dict = {
            'seq': seq if seq else (base_seq + index)
        }
        
        # Kanji element
        if has_kanji(term) and term != reading:
            k_ele = {'keb': term}
            if score > 0:
                k_ele['pri'] = ['spec1']
            entry_dict['k_ele'] = [k_ele]
        
        # Reading element
        r_ele = {'reb': reading if reading else term}
        if score > 0:
            r_ele['pri'] = ['spec1']
        if has_kanji(term) and term != reading and reading:
            r_ele['restr'] = [term]
        entry_dict['r_ele'] = [r_ele]
        
        # Senses
        senses = []
        for gloss in glosses:
            if gloss and gloss.strip():
                sense = {'gloss': [gloss]}
                
                if pos_array:
                    sense['pos'] = pos_array
                
                misc = []
                if def_tags and def_tags.strip():
                    misc.append(def_tags.strip())
                if misc:
                    sense['misc'] = misc
                
                senses.append(sense)
        
        if not senses:
            return None, False
        
        entry_dict['sense'] = senses
        return entry_dict, True
        
    except Exception as e:
        return None, False


def process_file(filepath, base_seq):
    """Process one file"""
    print(f"Processing: {filepath.name}")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            print(f"  ✗ Not an array")
            return [], 0, 0, base_seq
        
        entries = []
        converted = 0
        skipped = 0
        
        for i, entry in enumerate(data):
            result, success = convert_entry(entry, i, base_seq)
            if success and result:
                entries.append(result)
                converted += 1
                base_seq += 1
            else:
                skipped += 1
        
        print(f"  ✓ Converted: {converted}, Skipped: {skipped}")
        return entries, converted, skipped, base_seq
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return [], 0, 0, base_seq


def main():
    """Main"""
    print("=" * 60)
    print("Daijisen to JMDict Converter")
    print("With proper noun and media title filtering")
    print("=" * 60)
    
    files = sorted(Path('.').glob('term_bank_*.json'))
    
    if not files:
        print("\n✗ No term_bank files found")
        return
    
    print(f"\nFound {len(files)} files\n")
    
    all_entries = []
    total_conv = 0
    total_skip = 0
    base_seq = 50000
    
    for f in files:
        entries, conv, skip, base_seq = process_file(f, base_seq)
        all_entries.extend(entries)
        total_conv += conv
        total_skip += skip
    
    if not all_entries:
        print("\n✗ No entries converted!")
        return
    
    # Write output
    output = 'JMdict_converted.json'
    print(f"\nWriting: {output}")
    
    with open(output, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(all_entries, f, ensure_ascii=False, separators=(',', ':'))
    
    # Preview
    preview = 'JMdict_converted_preview.json'
    with open(preview, 'w', encoding='utf-8') as f:
        json.dump(all_entries[:20], f, ensure_ascii=False, indent=2)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Files: {len(files)}")
    print(f"Converted: {total_conv:,}")
    print(f"Skipped: {total_skip:,}")
    print(f"Success rate: {total_conv/(total_conv+total_skip)*100:.1f}%")
    print(f"Output: {output} ({os.path.getsize(output)/1024/1024:.1f} MB)")
    print(f"Preview: {preview} (20 entries)")
    print("=" * 60)
    print("✓ Done!")
    print("\nFiltering applied:")
    print("  - Place names (市の区名, etc.)")
    print("  - Media titles (映画, ドラマ, etc.)")
    print("  - Limited to 3 senses per entry")


if __name__ == '__main__':
    main()