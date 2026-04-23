#!/usr/bin/env python
"""
Automated Codebase Cleanup
Removes all temporary/development files safely
"""

import os
import shutil
from pathlib import Path

# Files to remove (temporary development files)
TEMP_FILES_TO_REMOVE = [
    # Database scripts
    'cleanup_database.py',
    'cleanup_mysql_files.py',
    'fix_analysis_creators.py',
    'fix_database_schema.py',
    'recover_database.py',
    'recover_database_direct.py',
    'reset_database_complete.py',
    
    # Migration scripts
    'migrate_annotations.py',
    'migrate_db.sql',
    'run_migration.py',
    'update_analysis_creators.py',
    
    # Test scripts
    'test_assignment_create.py',
    'test_phase5_clean.py',
    'test_phase6.py',
    'test_models.py',
    
    # Test output
    'test_output.txt',
    'phase5_test_results.txt',
    
    # Misc
    'copilot.txt',
    'user_accounts.txt',
    'start.bat',
]

# Files to keep (keep test_image_storage.py as reference)
FILES_TO_KEEP = [
    'test_image_storage.py',  # Reference for hospital-grade test
]

def cleanup():
    try:
        print("=" * 60)
        print("CODEBASE CLEANUP - REMOVING TEMPORARY FILES")
        print("=" * 60)
        
        workspace_dir = Path(__file__).parent
        removed_count = 0
        
        print("\nRemoving temporary files...")
        for filename in TEMP_FILES_TO_REMOVE:
            file_path = workspace_dir / filename
            
            if file_path.exists():
                try:
                    os.remove(file_path)
                    print(f"  ✓ Removed {filename}")
                    removed_count += 1
                except Exception as e:
                    print(f"  ✗ Failed to remove {filename}: {e}")
            else:
                print(f"  - {filename} (not found)")
        
        print(f"\n✓ Removed {removed_count} temporary files")
        
        # List remaining important files
        print("\n" + "=" * 60)
        print("PRODUCTION FILES (KEPT)")
        print("=" * 60)
        print("\nCore Files:")
        core_files = ['app.py', 'models.py', 'requirements.txt', '.env', '.gitignore']
        for f in core_files:
            if (workspace_dir / f).exists():
                print(f"  ✓ {f}")
        
        print("\nDirectories:")
        dirs = ['static', 'templates', 'uploads', 'models', 'images']
        for d in dirs:
            if (workspace_dir / d).exists():
                print(f"  ✓ {d}/")
        
        print("\nDocumentation:")
        docs = ['README.md', 'QUICKSTART.md', 'LESSONS_LEARNED.md', 'CLEANUP_GUIDE.md',
                'MYSQL_SETUP.md', 'XAMPP_SETUP.md', 'UI_IMPLEMENTATION_GUIDE.md']
        for doc in docs:
            if (workspace_dir / doc).exists():
                print(f"  ✓ {doc}")
        
        print("\n" + "=" * 60)
        print("✓ CLEANUP COMPLETE")
        print("=" * 60)
        print("\nYour codebase is now clean and production-ready!")
        print("\nNext steps:")
        print("  1. Review the CLEANUP_GUIDE.md for recommendations")
        print("  2. Run: git status (to verify deletions)")
        print("  3. Run: git add . && git commit -m 'Clean up: Remove temporary files'")
        print("  4. Your code is now ready for deployment! 🚀")
        
        return True
        
    except Exception as e:
        print(f"\n✗ CLEANUP FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    import sys
    success = cleanup()
    sys.exit(0 if success else 1)
