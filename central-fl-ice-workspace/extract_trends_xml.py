#!/usr/bin/env python3
"""
Extract population trends from ICE detention statistics Excel files
Uses XML parsing (no pandas/openpyxl required)
"""

import zipfile
import xml.etree.ElementTree as ET
import json
from pathlib import Path

# I-4 corridor facilities
I4_FACILITIES = [
    'PINELLAS COUNTY JAIL',
    'ORANGE COUNTY JAIL',
    'HILLSBOROUGH COUNTY JAIL'
]

def parse_xlsx_xml(filepath):
    """Parse XLSX using XML extraction"""
    results = {
        'shared_strings': [],
        'sheets': {}
    }
    
    try:
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
            
            # Read workbook
            sheet_map = {}
            with zf.open('xl/workbook.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for sheet in root.findall('.//main:sheet', ns):
                    name = sheet.get('name')
                    r_id = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                    sheet_map[r_id] = name
            
            # Read relationships
            sheet_files = {}
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
                        pass
    
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    
    return results

def find_i4_facilities(data, year):
    """Find I-4 corridor facilities in parsed data"""
    results = []
    
    for sheet_name, rows in data['sheets'].items():
        if 'facilit' not in sheet_name.lower():
            continue
        
        if not rows:
            continue
        
        # Get header row
        headers = rows[0] if rows else []
        
        # Look for I-4 facilities
        for row in rows[1:]:
            if not row:
                continue
            
            row_text = ' '.join(str(cell) for cell in row).upper()
            
            for facility_pattern in I4_FACILITIES:
                if facility_pattern in row_text:
                    record = {
                        'fiscal_year': year,
                        'sheet': sheet_name,
                        'raw_data': row[:20],  # First 20 columns
                        'headers': headers[:20]
                    }
                    results.append(record)
                    break
    
    return results

def main():
    excel_dir = Path('ICE-Detention-Stats')
    all_records = []
    
    years = ['FY20', 'FY21', 'FY22', 'FY23', 'FY24', 'FY25', 'FY26']
    
    for year in years:
        matching_files = list(excel_dir.glob(f'{year}*.xlsx'))
        if not matching_files:
            print(f"No file for {year}")
            continue
        
        filepath = matching_files[0]
        print(f"\nProcessing {filepath.name}...")
        
        data = parse_xlsx_xml(filepath)
        records = find_i4_facilities(data, year)
        
        if records:
            all_records.extend(records)
            print(f"  Found {len(records)} I-4 facilities")
        else:
            print(f"  No I-4 facilities found")
    
    # Save results
    with open('population_trends_raw.json', 'w') as f:
        json.dump(all_records, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Total records: {len(all_records)}")
    print(f"Saved to: population_trends_raw.json")
    
    # Show summary
    if all_records:
        print(f"\nYears with I-4 facilities:")
        year_facilities = {}
        for record in all_records:
            year = record['fiscal_year']
            if year not in year_facilities:
                year_facilities[year] = []
            year_facilities[year].append(record['raw_data'][0] if record['raw_data'] else 'Unknown')
        
        for year in sorted(year_facilities.keys()):
            print(f"  {year}: {', '.join(year_facilities[year])}")

if __name__ == '__main__':
    main()
