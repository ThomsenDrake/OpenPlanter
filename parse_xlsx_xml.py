#!/usr/bin/env python3
"""
Parse XLSX files using built-in zipfile module (no external dependencies)
XLSX files are ZIP archives containing XML files
"""

import zipfile
import xml.etree.ElementTree as ET
import json
import sys
from pathlib import Path

def parse_xlsx(filepath):
    """Parse an XLSX file and extract data"""
    results = {
        'sheets': {},
        'shared_strings': []
    }
    
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            # Get list of files in the archive
            file_list = zf.namelist()
            
            # Parse shared strings (lookup table for strings)
            if 'xl/sharedStrings.xml' in file_list:
                with zf.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    # Extract all string values
                    ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    for si in root.findall('.//main:si', ns):
                        t_elem = si.find('.//main:t', ns)
                        if t_elem is not None and t_elem.text:
                            results['shared_strings'].append(t_elem.text)
            
            # Parse workbook to get sheet names
            sheet_names = {}
            if 'xl/workbook.xml' in file_list:
                with zf.open('xl/workbook.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    for sheet in root.findall('.//main:sheet', ns):
                        sheet_id = sheet.get('sheetId')
                        name = sheet.get('name')
                        r_id = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                        sheet_names[sheet_id] = name
            
            # Parse each worksheet
            for file_path in file_list:
                if file_path.startswith('xl/worksheets/sheet') and file_path.endswith('.xml'):
                    with zf.open(file_path) as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                        
                        rows = []
                        for row in root.findall('.//main:row', ns):
                            row_data = []
                            row_num = row.get('r')
                            for cell in row.findall('main:c', ns):
                                cell_type = cell.get('t', 'n')  # n=number, s=shared string, str=string
                                value_elem = cell.find('main:v', ns)
                                if value_elem is not None and value_elem.text:
                                    if cell_type == 's':  # shared string
                                        try:
                                            idx = int(value_elem.text)
                                            if idx < len(results['shared_strings']):
                                                row_data.append(results['shared_strings'][idx])
                                            else:
                                                row_data.append(value_elem.text)
                                        except:
                                            row_data.append(value_elem.text)
                                    else:
                                        row_data.append(value_elem.text)
                                else:
                                    row_data.append('')
                            rows.append(row_data)
                        
                        # Get sheet number from filename
                        sheet_num = file_path.split('sheet')[1].split('.')[0]
                        sheet_name = sheet_names.get(sheet_num, f'Sheet{sheet_num}')
                        results['sheets'][sheet_name] = rows
            
            return results
            
    except Exception as e:
        return {'error': str(e)}

def search_for_counties(data, counties):
    """Search for I-4 corridor counties in the parsed data"""
    matches = []
    
    for sheet_name, rows in data.get('sheets', {}).items():
        for row_idx, row in enumerate(rows):
            row_text = ' '.join(str(cell) for cell in row)
            for county in counties:
                if county.lower() in row_text.lower():
                    matches.append({
                        'sheet': sheet_name,
                        'row_num': row_idx + 1,
                        'county': county,
                        'data': row
                    })
    
    return matches

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_xlsx_xml.py <xlsx_file>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    print(f"Parsing: {filepath}")
    
    data = parse_xlsx(filepath)
    
    if 'error' in data:
        print(f"Error: {data['error']}")
        return
    
    # Print summary
    print(f"\nSheets found: {len(data['sheets'])}")
    for sheet_name, rows in data['sheets'].items():
        print(f"  {sheet_name}: {len(rows)} rows")
    
    # Search for I-4 corridor counties
    counties = ['Hillsborough', 'Pinellas', 'Polk', 'Orange', 'Seminole', 'Volusia']
    matches = search_for_counties(data, counties)
    
    if matches:
        print(f"\nI-4 Corridor County References: {len(matches)}")
        for match in matches[:10]:  # Show first 10
            print(f"  - {match['county']} in {match['sheet']}, row {match['row_num']}")
            if match['data']:
                print(f"    Data: {' | '.join(str(c) for c in match['data'][:5])}")
    
    # Save full results
    output_file = Path(filepath).stem + '_parsed.json'
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\nFull data saved to: {output_file}")
    
    # Save matches
    if matches:
        matches_file = Path(filepath).stem + '_matches.json'
        with open(matches_file, 'w') as f:
            json.dump(matches, f, indent=2)
        print(f"Matches saved to: {matches_file}")

if __name__ == '__main__':
    main()
