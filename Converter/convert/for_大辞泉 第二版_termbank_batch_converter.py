#!/usr/bin/env python3
"""
Term Bank to JMDict Batch Converter
Processes multiple term_bank_*.json files and converts them to JMDict format
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime


def extract_text_from_structured_content(content):
    """Recursively extract text from structured content"""
    if content is None:
        return ''
    
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        return ''.join(extract_text_from_structured_content(item) for item in content)
    
    if isinstance(content, dict):
        if 'content' in content:
            return extract_text_from_structured_content(content['content'])
    
    return ''


def extract_definitions(structured_content):
    """Extract definitions from structured content"""
    definitions = []
    
    if not structured_content or not isinstance(structured_content, list):
        return definitions
    
    def find_meanings(content):
        if content is None:
            return
        
        if isinstance(content, list):
            for item in content:
                find_meanings(item)
        elif isinstance(content, dict):
            # Check if this element has meaning data
            if content.get('data', {}).get('meaning') is not None:
                text = extract_text_from_structured_content(content.get('content'))
                if text and text.strip():
                    definitions.append(text.strip())
            
            # Recursively search content
            if 'content' in content:
                find_meanings(content['content'])
    
    for def_item in structured_content:
        if def_item.get('type') == 'structured-content' and 'content' in def_item:
            find_meanings(def_item['content'])
    
    return definitions if definitions else ['']


def extract_part_of_speech(structured_content):
    """Extract part of speech from structured content"""
    pos = []
    
    if not structured_content or not isinstance(structured_content, list):
        return pos
    
    def find_hinshi(content):
        if content is None:
            return
        
        if isinstance(content, list):
            for item in content:
                find_hinshi(item)
        elif isinstance(content, dict):
            data = content.get('data', {})
            # Check for part of speech markers
            if 'hinshi' in data or 'FM' in data:
                text = extract_text_from_structured_content(content.get('content'))
                if text and text.strip():
                    pos.append(text.strip())
            
            if 'content' in content:
                find_hinshi(content['content'])
    
    for def_item in structured_content:
        if def_item.get('type') == 'structured-content' and 'content' in def_item:
            find_hinshi(def_item['content'])
    
    return pos


def has_kanji(text):
    """Check if text contains kanji characters"""
    return bool(re.search(r'[\u4e00-\u9faf]', text))


def convert_entry_to_jmdict(entry, index, base_seq=50000):
    """Convert a single term bank entry to JMDict format"""
    try:
        term = entry[0] if len(entry) > 0 else ''
        reading = entry[1] if len(entry) > 1 else ''
        def_tags = entry[2] if len(entry) > 2 else ''
        rules = entry[3] if len(entry) > 3 else ''
        score = entry[4] if len(entry) > 4 else 0
        definitions = entry[5] if len(entry) > 5 else []
        seq = entry[6] if len(entry) > 6 else None
        term_tags = entry[7] if len(entry) > 7 else ''
        
        jmdict_entry = {
            'seq': seq if seq else (base_seq + index)
        }
        
        # Add kanji element if term contains kanji
        term_has_kanji = has_kanji(term)
        if term_has_kanji and term != reading:
            jmdict_entry['k_ele'] = [{
                'keb': term
            }]
            
            # Add priority if score is high
            if score > 0:
                jmdict_entry['k_ele'][0]['pri'] = ['spec1']
        
        # Add reading element
        jmdict_entry['r_ele'] = [{
            'reb': reading if reading else term
        }]
        
        # Add priority to reading if score is high
        if score > 0:
            jmdict_entry['r_ele'][0]['pri'] = ['spec1']
        
        # If reading applies only to specific kanji
        if term_has_kanji and term != reading:
            jmdict_entry['r_ele'][0]['restr'] = [term]
        
        # Extract definitions and part of speech
        glosses = extract_definitions(definitions) if definitions else ['']
        pos_array = extract_part_of_speech(definitions) if definitions else []
        
        # Create sense entries
        jmdict_entry['sense'] = [{
            'gloss': [{'text': g, 'lang': 'eng'} for g in glosses if g]
        }]
        
        # Add part of speech if found
        if pos_array:
            jmdict_entry['sense'][0]['pos'] = [f'&{p};' for p in pos_array]
        
        # Add misc tags
        misc = []
        if def_tags:
            misc.append(f'&{def_tags};')
        if rules:
            misc.append(f'&{rules};')
        if misc:
            jmdict_entry['sense'][0]['misc'] = misc
        
        return jmdict_entry, True
    
    except Exception as e:
        print(f"  ⚠ Error converting entry {index}: {e}")
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
        return [], 0, 0, base_seq


def main():
    """Main function to process all term bank files"""
    print("=" * 60)
    print("Term Bank to JMDict Batch Converter")
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
    
    # Write output file - Just the array of entries, no wrapper
    output_file = 'jmdict_converted.json'
    print()
    print(f"Writing output to: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)
    
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
    print()
    print("✓ Conversion complete!")


if __name__ == '__main__':
    main()