#!/usr/bin/env python3
"""
Parse specific sheets from ICE detention statistics Excel files
Focus on the Facilities sheet which contains facility-level data
"""

import zipfile
import xml.etree.ElementTree as ET
import json
import sys
from pathlib import Path

def parse_all_sheets(filepath):
    """Parse all sheets from an XLSX file"""
    results = {
        'sheets': {},
        'shared_strings': []
    }
    
    with zipfile.ZipFile(filepath, 'r') as zf:
        # Parse shared strings
        if 'xl/sharedStrings.xml' in zf.namelist():
            with zf.open('xl/sharedStrings.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in root.findall('.//main:si', ns):
                    t_elem = si.find('.//main:t', ns)
                    if t_elem is not None and t_elem.text:
                        results['shared_strings'].append(t_elem.text)
        
        # Read workbook to get sheet mapping
        sheet_map = {}  # Maps sheet file to sheet name
        with zf.open('xl/workbook.xml') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            
            # Get relationship IDs
            for sheet in root.findall('.//main:sheet', ns):
                name = sheet.get('name')
                r_id = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                sheet_map[r_id] = name
        
        # Read workbook relationships to map r_id to sheet files
        sheet_files = {}  # Maps r_id to sheet file path
        with zf.open('xl/_rels/workbook.xml.rels') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'r': 'http://schemas.openxmlformats.org/package/2006/relationships'}
            for rel in root.findall('.//r:Relationship', ns):
                r_id = rel.get('Id')
                target = rel.get('Target')
                if 'worksheets/sheet' in target:
                    sheet_files[r_id] = target.replace('worksheets/', 'xl/worksheets/')
        
        # Parse each worksheet
        for r_id, sheet_name in sheet_map.items():
            if r_id in sheet_files:
                sheet_path = sheet_files[r_id]
                try:
                    with zf.open(sheet_path) as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                        
                        rows = []
                        for row in root.findall('.//main:row', ns):
                            row_data = []
                            for cell in row.findall('main:c', ns):
                                cell_type = cell.get('t', 'n')
                                value_elem = cell.find('main:v', ns)
                                if value_elem is not None and value_elem.text:
                                    if cell_type == 's':
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
                        
                        results['sheets'][sheet_name] = rows
                        
                except Exception as e:
                    print(f"Error reading sheet {sheet_name}: {e}")
    
    return results

def extract_florida_facilities(data):
    """Extract Florida facilities from the Facilities sheet"""
    florida_facilities = []
    
    facilities_sheet = data['sheets'].get('Facilities FY26') or data['sheets'].get('Facilities FY25')
    
    if not facilities_sheet:
        print("No Facilities sheet found")
        return florida_facilities
    
    # Find header row
    header_row = None
    for i, row in enumerate(facilities_sheet):
        if 'Facility' in str(row) or 'Name' in str(row):
            header_row = i
            break
    
    if header_row is None:
        print("Could not find header row")
        return florida_facilities
    
    print(f"Header row: {header_row}")
    print(f"Headers: {facilities_sheet[header_row][:10]}")
    
    # Look for Florida facilities in remaining rows
    for row in facilities_sheet[header_row+1:]:
        row_text = ' '.join(str(cell) for cell in row).upper()
        if 'FLORIDA' in row_text or 'TAMPA' in row_text or 'ORLANDO' in row_text or \
           'HILLSBOROUGH' in row_text or 'PINELLAS' in row_text or 'POLK' in row_text or \
           'ORANGE' in row_text or 'SEMINOLE' in row_text or 'VOLUSIA' in row_text:
            florida_facilities.append(row)
    
    return florida_facilities

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_facilities_sheet.py <xlsx_file>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    print(f"Parsing: {filepath}")
    
    data = parse_all_sheets(filepath)
    
    print(f"\nSheets found: {len(data['sheets'])}")
    for sheet_name in sorted(data['sheets'].keys()):
        print(f"  - {sheet_name}: {len(data['sheets'][sheet_name])} rows")
    
    # Extract Florida facilities
    fl_facilities = extract_florida_facilities(data)
    
    print(f"\nFlorida facilities found: {len(fl_facilities)}")
    for i, fac in enumerate(fl_facilities[:20], 1):
        print(f"{i}. {' | '.join(str(c)[:50] for c in fac[:8])}")
    
    # Save results
    output_file = Path(filepath).stem + '_facilities.json'
    with open(output_file, 'w') as f:
        json.dump({
            'florida_facilities': fl_facilities,
            'all_sheets': list(data['sheets'].keys())
        }, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_file}")

if __name__ == '__main__':
    main()
