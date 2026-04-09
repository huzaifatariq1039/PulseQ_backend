#!/usr/bin/env python3
"""
Automated Firebase to PostgreSQL Migration Script
Converts common Firebase Firestore patterns to SQLAlchemy PostgreSQL patterns
"""

import re
import os
from pathlib import Path

# Migration patterns
MIGRATIONS = [
    # Import replacements
    {
        'type': 'import',
        'pattern': r'from app\.config import COLLECTIONS',
        'replacement': 'from app.db_models import User, Doctor, Hospital, Token, ActivityLog'
    },
    {
        'type': 'import',
        'pattern': r'from app\.database import get_db\n',
        'replacement': 'from app.database import get_db, get_db_session\nfrom sqlalchemy.orm import Session\n'
    },
    
    # Simple document get patterns
    {
        'type': 'pattern',
        'pattern': r'db = get_db\(\)\n\s+([a-z_]+)_ref = db\.collection\(COLLECTIONS\["([A-Z_]+)"\]\)\.document\(([a-z_]+)\)\n\s+([a-z_]+)_doc = \1_ref\.get\(\)\n\s+if not \4_doc\.exists:',
        'replacement': lambda m: f'db = get_db_session()\n    {m.group(1)} = db.query({m.group(2).title()}).filter({m.group(2).title()}.id == {m.group(3)}).first()\n    if not {m.group(1)}:'
    },
    
    # Document to_dict conversion
    {
        'type': 'pattern', 
        'pattern': r'([a-z_]+)_data = ([a-z_]+)_doc\.to_dict\(\)',
        'replacement': r'\1_data = \1.__dict__ if \1 else {}'
    },
    {
        'type': 'pattern',
        'pattern': r'([a-z_]+)_data = ([a-z_]+)_ref\.get\(\)\.to_dict\(\)',
        'replacement': lambda m: f'db = get_db_session()\n    {m.group(1)} = db.query({m.group(2).title()}).filter({m.group(2).title()}.id == {m.group(2)}_id).first()\n    {m.group(1)}_data = {m.group(1)}.__dict__ if {m.group(1)} else {{}}'
    },
    
    # Collection queries
    {
        'type': 'pattern',
        'pattern': r'([a-z_]+)_ref = db\.collection\(COLLECTIONS\["([A-Z_]+)"\]\)',
        'replacement': r''  # Remove, will be replaced with query
    },
    {
        'type': 'pattern',
        'pattern': r'query = \1_ref\.where\("([a-z_]+)", "==", ([a-z_]+)\)',
        'replacement': r'\1s = db.query(\2).filter(\2.\1 == \3).all()'
    },
    
    # Document set/create
    {
        'type': 'pattern',
        'pattern': r'db\.collection\(COLLECTIONS\["([A-Z_]+)"\]\)\.document\(([a-z_]+)\)\.set\(([a-z_]+)\)',
        'replacement': lambda m: f'{m.group(2).lower()} = {m.group(1).title()}(id={m.group(2)}, **{m.group(3)})\n    db.add({m.group(2).lower()})\n    db.commit()'
    },
    
    # Document update
    {
        'type': 'pattern',
        'pattern': r'([a-z_]+)_ref\.update\(\{([^}]+)\}\)',
        'replacement': lambda m: f'# TODO: Update {m.group(1)} with: {m.group(2)}'
    },
    
    # User lookups
    {
        'type': 'pattern',
        'pattern': r'user_ref = db\.collection\(COLLECTIONS\["USERS"\]\)\.document\(([a-z_]+)\)\n\s+user_data = user_ref\.get\(\)\.to_dict\(\)',
        'replacement': r'db = get_db_session()\n    user = db.query(User).filter(User.id == \1).first()\n    user_data = user.__dict__ if user else {}'
    },
    
    # Activity logging
    {
        'type': 'pattern',
        'pattern': r'activities_ref = db\.collection\("activities"\)\n\s+activity_ref = activities_ref\.document\(\)',
        'replacement': 'import uuid\n    activity_id = str(uuid.uuid4())'
    },
]

def migrate_file(file_path):
    """Migrate a single file from Firebase to PostgreSQL"""
    print(f"\n{'='*60}")
    print(f"Migrating: {file_path}")
    print(f"{'='*60}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    changes_made = 0
    
    # Apply migrations
    for migration in MIGRATIONS:
        if migration['type'] == 'import':
            if re.search(migration['pattern'], content):
                content = re.sub(migration['pattern'], migration['replacement'], content)
                changes_made += 1
                print(f"  ✓ Import replacement applied")
        elif migration['type'] == 'pattern':
            if callable(migration['replacement']):
                # Complex replacement
                new_content = re.sub(migration['pattern'], migration['replacement'], content)
                if new_content != content:
                    content = new_content
                    changes_made += 1
                    print(f"  ✓ Pattern migration applied")
            else:
                if re.search(migration['pattern'], content):
                    content = re.sub(migration['pattern'], migration['replacement'], content)
                    changes_made += 1
                    print(f"  ✓ Simple pattern replaced")
    
    if changes_made > 0:
        # Backup original
        backup_path = file_path + '.backup'
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"  ✓ Backup created: {backup_path}")
        
        # Write migrated content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ File migrated: {changes_made} changes")
    else:
        print(f"  ⚠ No changes needed")
    
    return changes_made

def main():
    """Main migration function"""
    print("🚀 Firebase to PostgreSQL Migration Script")
    print("=" * 60)
    
    # Files to migrate
    files_to_migrate = [
        'app/routes/tokens.py',
        'app/routes/doctors.py',
        'app/routes/hospitals.py',
        'app/routes/dashboard.py',
        'app/routes/payments.py',
        'app/routes/portal.py',
        'app/routes/consultation.py',
        'app/routes/profile.py',
        'app/routes/pharmacy.py',
        'app/routes/patient.py',
        'app/routes/pos.py',
        'app/routes/reception.py',
    ]
    
    base_path = Path(__file__).parent
    total_changes = 0
    files_migrated = 0
    
    for file_path in files_to_migrate:
        full_path = base_path / file_path
        if full_path.exists():
            changes = migrate_file(str(full_path))
            total_changes += changes
            if changes > 0:
                files_migrated += 1
        else:
            print(f"\n⚠ File not found: {file_path}")
    
    print(f"\n{'='*60}")
    print(f"✅ Migration Complete!")
    print(f"{'='*60}")
    print(f"Files migrated: {files_migrated}")
    print(f"Total changes: {total_changes}")
    print(f"\n⚠️  IMPORTANT: Review all migrated files before deploying!")
    print(f"   - Check for TODO comments")
    print(f"   - Test all endpoints")
    print(f"   - Verify database queries")

if __name__ == '__main__':
    main()
