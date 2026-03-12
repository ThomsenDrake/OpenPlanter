#!/usr/bin/env python3
"""
Extract I-4 corridor ICE detention facilities from all Excel files
"""

import zipfile
import xml.etree.ElementTree as ET
import json
from pathlib import Path

# I-4 corridor counties in Florida
I4_COUNTIES_FL = ['HILLSBOROUGH', 'PINELLAS', 'POLK', 'ORANGE', 'SEMINOLE', 'VOLUSIA']

def parse_facilities_sheet(filepath):
    """Parse the Facilities sheet from an Excel file"""
    results = {'shared_strings': [], 'facilities': []}
    
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
            
            # Read workbook to get sheet mapping
            sheet_map = {}
            with zf.open('xl/workbook.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for sheet in root.findall('.//main:sheet', ns):
                    name = sheet.get('name')
                    r_id = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                    sheet_map[r_id] = name
            
            # Read workbook relationships
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
            
            # Find Facilities sheet
            facilities_rid = None
            for r_id, name in sheet_map.items():
                if 'Facilities' in name:
                    facilities_rid = r_id
                    break
            
            if not facilities_rid or facilities_rid not in sheet_files:
                return results
            
            # Parse Facilities sheet
            sheet_path = sheet_files[facilities_rid]
            with zf.open(sheet_path) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                
                # Get all rows
                all_rows = []
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
                    all_rows.append(row_data)
                
                results['facilities'] = all_rows
                
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
    
    return results

def extract_i4_facilities(facilities_data, fiscal_year):
    """Extract I-4 corridor facilities from parsed data"""
    i4_facilities = []
    
    # Find header row
    header_row = None
    for i, row in enumerate(facilities_data):
        if 'Facility' in str(row) or 'Name' in str(row):
            header_row = i
            break
    
    if header_row is None:
        return i4_facilities
    
    # Extract facilities that are in Florida AND in I-4 corridor counties
    # Column structure: [0]=name, [1]=address, [2]=city, [3]=state, [4]=zip, [5]=area, [6]=type, [7]=gender
    for row in facilities_data[header_row+1:]:
        if len(row) < 8:
            continue
        
        name = str(row[0]).strip().upper() if len(row) > 0 else ''
        address = str(row[1]).strip() if len(row) > 1 else ''
        city = str(row[2]).strip() if len(row) > 2 else ''
        state = str(row[3]).strip().upper() if len(row) > 3 else ''
        zip_code = str(row[4]).strip() if len(row) > 4 else ''
        area = str(row[5]).strip() if len(row) > 5 else ''
        facility_type = str(row[6]).strip() if len(row) > 6 else ''
        gender = str(row[7]).strip() if len(row) > 7 else ''
        
        # Must be in Florida
        if state != 'FL':
            continue
        
        # Check if it's in I-4 corridor (by county name or city)
        is_i4 = False
        county_found = None
        
        for county in I4_COUNTIES_FL:
            if county in name or (county == 'HILLSBOROUGH' and 'TAMPA' in city.upper()):
                is_i4 = True
                county_found = county
                break
        
        # Special case for cities in I-4 corridor
        if not is_i4:
            i4_cities = {
                'TAMPA': 'HILLSBOROUGH',
                'CLEARWATER': 'PINELLAS',
                'ST. PETERSBURG': 'PINELLAS',
                'LAKELAND': 'POLK',
                'ORLANDO': 'ORANGE',
                'SANFORD': 'SEMINOLE',
                'DAYTONA BEACH': 'VOLUSIA'
            }
            
            city_upper = city.upper()
            for i4_city, county in i4_cities.items():
                if i4_city in city_upper:
                    is_i4 = True
                    county_found = county
                    break
        
        if is_i4:
            i4_facilities.append({
                'fiscal_year': fiscal_year,
                'name': name,
                'address': address,
                'city': city,
                'state': state,
                'zip': zip_code,
                'area': area,
                'type': facility_type,
                'gender': gender,
                'county': county_found
            })
    
    return i4_facilities

def main():
    excel_dir = Path('ICE-Detention-Stats')
    all_i4_facilities = []
    
    # Process each Excel file
    for excel_file in sorted(excel_dir.glob('*.xlsx')):
        print(f"\nProcessing: {excel_file.name}")
        
        # Extract fiscal year from filename
        parts = excel_file.stem.split('_')
        fy = parts[0]  # e.g., "FY26"
        
        data = parse_facilities_sheet(excel_file)
        
        if data['facilities']:
            print(f"  Facilities sheet: {len(data['facilities'])} rows")
            
            i4_facs = extract_i4_facilities(data['facilities'], fy)
            
            if i4_facs:
                print(f"  I-4 corridor facilities: {len(i4_facs)}")
                all_i4_facilities.extend(i4_facs)
                
                for fac in i4_facs:
                    print(f"    - {fac['name']} ({fac['city']}, {fac['county']} County)")
        else:
            print(f"  No facilities data found")
    
    print(f"\n{'='*60}")
    print(f"Total I-4 corridor facility records: {len(all_i4_facilities)}")
    
    # Group by facility name
    facility_groups = {}
    for fac in all_i4_facilities:
        name = fac['name']
        if name not in facility_groups:
            facility_groups[name] = []
        facility_groups[name].append(fac)
    
    print(f"\nUnique facilities: {len(facility_groups)}")
    for name, records in sorted(facility_groups.items()):
        years = [r['fiscal_year'] for r in records]
        print(f"  - {name}: {years}")
    
    # Save results
    with open('i4_facilities_all_years.json', 'w') as f:
        json.dump(all_i4_facilities, f, indent=2)
    
    with open('i4_facilities_grouped.json', 'w') as f:
        json.dump(facility_groups, f, indent=2)
    
    print(f"\nResults saved to:")
    print(f"  - i4_facilities_all_years.json")
    print(f"  - i4_facilities_grouped.json")

if __name__ == '__main__':
    main()
