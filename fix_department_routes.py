#!/usr/bin/env python3
"""
Script to fix route ordering in doctors.py
Moves POST/PUT/DELETE department endpoints BEFORE GET /departments
to fix 405 Method Not Allowed error
"""

import os
import re

def fix_route_ordering():
    """Fix the route ordering in doctors.py"""
    file_path = os.path.join(os.path.dirname(__file__), 'app', 'routes', 'doctors.py')
    
    print(f"Reading {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the section with GET /departments
    get_departments_pattern = r'(@router\.get\("/departments".*?return \{"success": True, "data": out\})'
    
    # Find the section with department management endpoints
    dept_mgmt_pattern = r'(# ==================== DEPARTMENT MANAGEMENT.*?return ok\(message="Department deleted successfully"\))'
    
    get_match = re.search(get_departments_pattern, content, re.DOTALL)
    dept_mgmt_match = re.search(dept_mgmt_pattern, content, re.DOTALL)
    
    if not get_match or not dept_mgmt_match:
        print("ERROR: Could not find the required sections!")
        print(f"GET match: {get_match is not None}")
        print(f"Dept Mgmt match: {dept_mgmt_match is not None}")
        return False
    
    get_section = get_match.group(1)
    dept_mgmt_section = dept_mgmt_match.group(1)
    
    # Replace: Remove both sections and re-insert in correct order
    # First, remove the department management section
    content = content.replace(dept_mgmt_section, '')
    
    # Now replace the GET /departments section with reordered versions
    content = content.replace(
        get_section,
        dept_mgmt_section + '\n\n\n' + get_section
    )
    
    # Clean up extra blank lines
    content = re.sub(r'\n{4,}', '\n\n\n', content)
    
    # Write back
    print("Writing updated content...")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Successfully reordered department endpoints!")
    print("📍 New order:")
    print("   1. POST   /departments (Create)")
    print("   2. GET    /departments/list (List all)")
    print("   3. PUT    /departments/{id} (Update)")
    print("   4. PATCH  /departments/{id} (Update)")
    print("   5. DELETE /departments/{id} (Delete)")
    print("   6. GET    /departments (List names - legacy)")
    return True

if __name__ == "__main__":
    try:
        fix_route_ordering()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
