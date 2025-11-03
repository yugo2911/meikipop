#!/usr/bin/env python3
"""
Term Bank to JMdict Batch Converter
Processes multiple term_bank_*.json files and converts them to JMDict format
Compatible with the nazeka/wareya JMdict JSON format
"""

import json
import os
import re
from pathlib import Path


def extract_text_from_structured_content(content, skip_names=None):
    """
    Recursively extract text from structured content
    If skip_names is provided, skip elements with those names
    """
    if content is None:
        return ''
    
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        texts = []
        for item in content:
            text = extract_text_from_structured_content(item, skip_names)
            if text:
                texts.append(text)
        return ''.join(texts)
    
    if isinstance(content, dict):
        # Check if this element should be skipped
        if skip_names:
            elem_name = content.get('data', {}).get('name', '')
            if elem_name in skip_names:
                return ''
        
        # Skip image tags
        if content.get('tag') == 'img':
            return ''
        
        # Recursively extract from content
        if 'content' in content:
            return extract_text_from_structured_content(content['content'], skip_names)
    
    return ''


def split_definitions_by_markers(text):
    """
    Split text into multiple definitions based on numbered markers
    ① ② ③ or (1) (2) (3) or 1. 2. 3.
    """
    if not text:
        return [text]
    
    # Look for circled numbers ①②③ or parenthesized numbers (1)(2)(3)
    pattern = r'[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]|\(\d+\)|\d+\s*[.、]'
    
    # Split but keep the markers
    parts = re.split(f'({pattern})', text)
    
    definitions = []
    current_def = ''
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Check if this is a marker
        if re.match(pattern, part):
            # Save previous definition if exists
            if current_def.strip():
                definitions.append(current_def.strip())
            current_def = part + ' '
        else:
            current_def += part
    
    # Add the last definition
    if current_def.strip():
        definitions.append(current_def.strip())
    
    # If no splits happened, return as single definition
    return definitions if len(definitions) > 1 else [text]


def clean_definition_text(text):
    """Clean up definition text"""
    if not text:
        return ''
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def extract_definitions_from_structured(structured_content):
    """Extract definitions from structured content, handling multiple senses"""
    if not structured_content or not isinstance(structured_content, list):
        return []
    
    all_definitions = []
    
    for def_item in structured_content:
        if not isinstance(def_item, dict):
            continue
            
        if def_item.get('type') != 'structured-content':
            continue
        
        content = def_item.get('content', [])
        if not isinstance(content, list):
            continue
        
        # Extract all definition text
        def find_definitions(elem, depth=0):
            if not isinstance(elem, dict):
                return
            
            name = elem.get('data', {}).get('name', '')
            
            # Extract from definition fields
            if name in ['語釈', '語義', '解説', '意味']:
                # Skip certain sub-elements that are metadata
                skip_names = ['かぞえ方解説', 'かぞえ方解説M', '補足ロゴG', '補足ロゴ']
                text = extract_text_from_structured_content(elem.get('content'), skip_names=skip_names)
                if text and text.strip():
                    text = clean_definition_text(text)
                    if text:
                        # Split by numbered markers if present
                        split_defs = split_definitions_by_markers(text)
                        all_definitions.extend(split_defs)
                return
            
            # Recursively search
            if 'content' in elem:
                content = elem['content']
                if isinstance(content, list):
                    for item in content:
                        find_definitions(item, depth + 1)
                else:
                    find_definitions(content, depth + 1)
        
        for elem in content:
            find_definitions(elem)
    
    return all_definitions if all_definitions else ['']


def extract_reading_from_structured(structured_content):
    """Extract reading (kana) from structured content if not provided"""
    if not structured_content or not isinstance(structured_content, list):
        return None
    
    for def_item in structured_content:
        if not isinstance(def_item, dict):
            continue
            
        if def_item.get('type') != 'structured-content':
            continue
        
        # Look for 見出仮名 (headword kana)
        content = def_item.get('content', [])
        if isinstance(content, list):
            for elem in content:
                if not isinstance(elem, dict):
                    continue
                if elem.get('data', {}).get('name') == '見出仮名':
                    text = extract_text_from_structured_content(elem.get('content'))
                    if text:
                        # Clean up reading (remove spaces and special chars)
                        text = text.strip().replace(' ', '').replace('　', '')
                        return text
    
    return None


def extract_part_of_speech_from_structured(structured_content):
    """Extract part of speech from structured content"""
    if not structured_content or not isinstance(structured_content, list):
        return []
    
    pos_list = []
    
    for def_item in structured_content:
        if not isinstance(def_item, dict):
            continue
            
        if def_item.get('type') != 'structured-content':
            continue
        
        content = def_item.get('content', [])
        
        def find_pos(elem):
            if not isinstance(elem, dict):
                return
            
            name = elem.get('data', {}).get('name', '')
            
            # Look for part of speech indicators
            if name in ['品詞', 'hinshi', 'FM', '品詞G']:
                text = extract_text_from_structured_content(elem.get('content'))
                if text and text.strip():
                    cleaned = text.strip()
                    # Remove the 〘 〙 brackets if present
                    cleaned = cleaned.replace('〘', '').replace('〙', '').strip()
                    if cleaned:
                        pos_list.append(cleaned)
                return
            
            # Recursively search
            if 'content' in elem:
                content = elem['content']
                if isinstance(content, list):
                    for item in content:
                        find_pos(item)
                else:
                    find_pos(content)
        
        if isinstance(content, list):
            for elem in content:
                find_pos(elem)
    
    return pos_list


def has_kanji(text):
    """Check if text contains kanji characters"""
    if not text:
        return False
    return bool(re.search(r'[\u4e00-\u9faf]', text))


def convert_entry_to_jmdict(entry, index, base_seq=50000):
    """Convert a single term bank entry to JMDict format matching nazeka/wareya structure"""
    try:
        # Parse term bank format: [term, reading, def_tags, rules, score, definitions, seq, term_tags]
        term = entry[0] if len(entry) > 0 else ''
        reading = entry[1] if len(entry) > 1 else ''
        def_tags = entry[2] if len(entry) > 2 else ''
        rules = entry[3] if len(entry) > 3 else ''
        score = entry[4] if len(entry) > 4 else 0
        definitions = entry[5] if len(entry) > 5 else []
        seq = entry[6] if len(entry) > 6 else None
        term_tags = entry[7] if len(entry) > 7 else ''
        
        # If reading is empty or same as term, try to extract from structured content
        if not reading or reading == term:
            extracted_reading = extract_reading_from_structured(definitions)
            if extracted_reading:
                reading = extracted_reading
        
        # Clean up reading (remove spaces)
        if reading:
            reading = reading.replace(' ', '').replace('　', '')
        
        # Create JMdict entry
        jmdict_entry = {
            'seq': seq if seq else (base_seq + index)
        }
        
        # Add kanji element if term contains kanji
        term_has_kanji = has_kanji(term)
        if term_has_kanji and term != reading:
            k_ele = {'keb': term}
            
            # Add priority if score is high
            if score > 0:
                k_ele['pri'] = ['spec1']
            
            jmdict_entry['k_ele'] = [k_ele]
        
        # Add reading element (always required)
        r_ele = {'reb': reading if reading else term}
        
        # Add priority to reading if score is high
        if score > 0:
            r_ele['pri'] = ['spec1']
        
        # If reading applies only to specific kanji
        if term_has_kanji and term != reading and reading:
            r_ele['restr'] = [term]
        
        jmdict_entry['r_ele'] = [r_ele]
        
        # Extract definitions and part of speech from structured content
        glosses = extract_definitions_from_structured(definitions)
        pos_array = extract_part_of_speech_from_structured(definitions)
        
        # Create sense entries - one per definition if multiple definitions found
        senses = []
        
        # If we have multiple definitions, create separate senses
        valid_glosses = [g for g in glosses if g and g.strip()]
        
        if not valid_glosses:
            # No definitions found, skip this entry
            return None, False
        
        for gloss in valid_glosses:
            sense = {}
            
            # Add part of speech (same for all senses in this entry)
            if pos_array:
                sense['pos'] = pos_array
            
            # Add misc tags
            misc = []
            if def_tags and def_tags.strip():
                misc.append(def_tags.strip())
            if rules and rules.strip():
                misc.append(rules.strip())
            if misc:
                sense['misc'] = misc
            
            # Add the gloss
            sense['gloss'] = [gloss]
            
            senses.append(sense)
        
        jmdict_entry['sense'] = senses
        
        return jmdict_entry, True
    
    except Exception as e:
        print(f"  ⚠ Error converting entry {index}: {e}")
        import traceback
        traceback.print_exc()
        return None, False


def process_term_bank_file(filepath, base_seq):
    """Process a single term bank JSON file"""
    print(f"Processing: {filepath.name}")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            print(f"  ✗ Skipped: Not an array")
            return [], 0, 0, base_seq
        
        entries = []
        converted = 0
        skipped = 0
        
        for i, entry in enumerate(data):
            jmdict_entry, success = convert_entry_to_jmdict(entry, i, base_seq)
            if success and jmdict_entry:
                entries.append(jmdict_entry)
                converted += 1
                base_seq += 1
            else:
                skipped += 1
        
        print(f"  ✓ Converted: {converted}, Skipped: {skipped}")
        return entries, converted, skipped, base_seq
    
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON Error: {e}")
        return [], 0, 0, base_seq
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return [], 0, 0, base_seq


def main():
    """Main function to process all term bank files"""
    print("=" * 60)
    print("Term Bank to JMdict Batch Converter")
    print("=" * 60)
    
    # Get current directory
    current_dir = Path('.')
    
    # Find all term_bank_*.json files
    term_bank_files = sorted(current_dir.glob('term_bank_*.json'))
    
    if not term_bank_files:
        print("\n✗ No term_bank_*.json files found in current directory")
        return
    
    print(f"\nFound {len(term_bank_files)} term bank files")
    print()
    
    all_entries = []
    total_converted = 0
    total_skipped = 0
    base_seq = 50000
    
    # Process each file
    for filepath in term_bank_files:
        entries, converted, skipped, base_seq = process_term_bank_file(filepath, base_seq)
        all_entries.extend(entries)
        total_converted += converted
        total_skipped += skipped
    
    if not all_entries:
        print("\n✗ No entries were successfully converted!")
        return
    
    # Write output file
    output_file = 'JMdict_converted.json'
    print()
    print(f"Writing output to: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(all_entries, f, ensure_ascii=False, separators=(',', ':'))
    
    # Also create a pretty-printed version for inspection
    preview_file = 'JMdict_converted_preview.json'
    with open(preview_file, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(all_entries[:10], f, ensure_ascii=False, indent=2)
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Files processed: {len(term_bank_files)}")
    print(f"Total entries converted: {total_converted}")
    print(f"Total entries skipped: {total_skipped}")
    print(f"Output file: {output_file}")
    print(f"File size: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB")
    print(f"Preview file (first 10 entries): {preview_file}")
    print()
    print("✓ Conversion complete!")
    print(f"\nMove {output_file} to your data/ folder to use it.")


if __name__ == '__main__':
    main()