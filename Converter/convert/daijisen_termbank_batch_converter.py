#!/usr/bin/env python3
"""
Daijisen Term Bank to JMDict Batch Converter
Processes multiple term_bank_*.json files and converts them to JMDict format
Optimized for 大辞泉 dictionary structure with filtered, concise output
"""

import json
import os
import re
from pathlib import Path


def extract_all_text(elem, skip_tags=None):
    """Extract all text from element, skipping certain tags"""
    if elem is None:
        return ''
    
    if isinstance(elem, str):
        return elem
    
    if isinstance(elem, list):
        return ''.join(extract_all_text(item, skip_tags) for item in elem)
    
    if isinstance(elem, dict):
        # Skip img tags
        if elem.get('tag') == 'img':
            return ''
        
        # Skip certain tagged elements
        if skip_tags and elem.get('tag') in skip_tags:
            return ''
        
        # Extract from content
        if 'content' in elem:
            return extract_all_text(elem['content'], skip_tags)
    
    return ''


def clean_definition(text):
    """Clean and limit definition text"""
    if not text:
        return ''
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Remove references like (→word)
    text = re.sub(r'[（(]→[^)）]+[)）]', '', text)
    
    # Limit length
    MAX_LENGTH = 250
    if len(text) > MAX_LENGTH:
        cut = text[:MAX_LENGTH].rfind('。')
        if cut > 150:
            text = text[:cut + 1]
        else:
            text = text[:MAX_LENGTH] + '...'
    
    return text.strip()


def split_into_senses(text):
    """Split text by numbered markers into separate senses"""
    if not text:
        return []
    
    # Split by circled numbers or parenthesized letters
    parts = re.split(r'([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]|㋐|㋑|㋒|㋓|㋔)', text)
    
    senses = []
    current = ''
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Check if marker
        if re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮㋐㋑㋒㋓㋔]$', part):
            if current.strip():
                cleaned = clean_definition(current)
                if cleaned:
                    senses.append(cleaned)
            current = ''
        else:
            current += part
    
    # Add last sense
    if current.strip():
        cleaned = clean_definition(current)
        if cleaned:
            senses.append(cleaned)
    
    # If no splits, return whole text
    if not senses:
        cleaned = clean_definition(text)
        return [cleaned] if cleaned else []
    
    # Limit to 5 most important senses
    return senses[:5]


def extract_definitions(structured_content):
    """Extract definitions from structured content - simplified approach"""
    if not structured_content or not isinstance(structured_content, list):
        return []
    
    # Skip these tags completely
    skip_tags = {'img'}
    
    all_text = ''
    
    for item in structured_content:
        if not isinstance(item, dict):
            continue
        
        if item.get('type') == 'structured-content':
            # Extract all text from this structured content
            text = extract_all_text(item.get('content', []), skip_tags)
            if text:
                all_text += text + ' '
    
    all_text = all_text.strip()
    
    if not all_text:
        return []
    
    # Now intelligently filter the text
    # Look for actual definition content (after the headword section)
    
    # Try to find where definitions start (usually after 】 bracket)
    def_start = all_text.find('】')
    if def_start != -1:
        all_text = all_text[def_start + 1:].strip()
    
    # Remove accent marks and symbols
    all_text = re.sub(r'[⓪①②③④⑤⑥⑦⑧⑨](?!\s*[あ-ん])', '', all_text)
    
    # Remove 【kanji】 notation blocks at start
    all_text = re.sub(r'^【[^】]+】\s*', '', all_text)
    
    # Try to extract just the core definition parts
    # Split into sentences and filter
    sentences = []
    
    # First try to split by sense markers
    if re.search(r'[①②③④⑤⑥⑦⑧⑨⑩]', all_text):
        return split_into_senses(all_text)
    
    # Otherwise, take first few meaningful sentences
    # Split by 。but keep sentences
    parts = all_text.split('。')
    for part in parts[:3]:  # Max 3 sentences
        part = part.strip()
        if len(part) > 10:  # Skip very short parts
            sentences.append(part + '。')
    
    if sentences:
        result = clean_definition(''.join(sentences))
        return [result] if result else []
    
    # Fallback: just clean and return first 250 chars
    cleaned = clean_definition(all_text)
    return [cleaned] if cleaned else []


def extract_reading(structured_content, fallback_reading):
    """Extract reading from structured content"""
    if not structured_content or not isinstance(structured_content, list):
        return fallback_reading
    
    for item in structured_content:
        if not isinstance(item, dict):
            continue
        
        if item.get('type') != 'structured-content':
            continue
        
        # Look for reading in the structure
        def find_reading(elem):
            if not isinstance(elem, dict):
                return None
            
            name = elem.get('data', {}).get('name', '')
            if name == '見出仮名':
                text = extract_all_text(elem.get('content'))
                if text:
                    # Clean reading
                    text = text.replace(' ', '').replace('　', '')
                    text = re.sub(r'[⓪①②③④⑤⑥⑦⑧⑨]', '', text)
                    text = text.replace('【', '').replace('】', '')
                    return text.strip()
            
            # Recurse
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
        
        # Get definitions
        glosses = extract_definitions(definitions)
        
        if not glosses or not any(g for g in glosses):
            return None, False
        
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
                
                # Add misc if present
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
        print(f"    Error at {index}: {e}")
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
        print("Check if term_bank files have the expected structure.")
        return
    
    # Write output
    output = 'JMdict_converted.json'
    print(f"\nWriting: {output}")
    
    with open(output, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(all_entries, f, ensure_ascii=False, separators=(',', ':'))
    
    # Preview
    preview = 'JMdict_converted_preview.json'
    with open(preview, 'w', encoding='utf-8') as f:
        json.dump(all_entries[:10], f, ensure_ascii=False, indent=2)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Files: {len(files)}")
    print(f"Converted: {total_conv:,}")
    print(f"Skipped: {total_skip:,}")
    print(f"Output: {output} ({os.path.getsize(output)/1024/1024:.1f} MB)")
    print(f"Preview: {preview}")
    print("=" * 60)
    print("✓ Done!")


if __name__ == '__main__':
    main()
