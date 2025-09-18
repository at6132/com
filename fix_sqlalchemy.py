#!/usr/bin/env python3
"""
Quick fix for SQLAlchemy typing compatibility issue
"""
import subprocess
import sys

def fix_sqlalchemy():
    """Fix SQLAlchemy typing issue"""
    print("🔧 Fixing SQLAlchemy typing compatibility issue...")
    
    try:
        # Uninstall current SQLAlchemy
        print("Uninstalling current SQLAlchemy...")
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "sqlalchemy", "-y"], 
                      check=True, capture_output=True, text=True)
        
        # Install compatible version
        print("Installing SQLAlchemy 2.0.25...")
        subprocess.run([sys.executable, "-m", "pip", "install", "sqlalchemy[asyncio]==2.0.25"], 
                      check=True, capture_output=True, text=True)
        
        # Test import
        print("Testing SQLAlchemy import...")
        import sqlalchemy
        from sqlalchemy import create_engine
        from sqlalchemy.ext.asyncio import create_async_engine
        
        print(f"✅ SQLAlchemy {sqlalchemy.__version__} installed and working!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to fix SQLAlchemy: {e}")
        return False
    except ImportError as e:
        print(f"❌ SQLAlchemy import still failing: {e}")
        return False

if __name__ == "__main__":
    if fix_sqlalchemy():
        print("\n🎉 SQLAlchemy fix completed successfully!")
        print("You can now run: python setup_environment.py")
    else:
        print("\n❌ SQLAlchemy fix failed. Please check your Python version.")
        print("This issue typically occurs with Python 3.11+ and certain SQLAlchemy versions.")
