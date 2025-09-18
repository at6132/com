#!/usr/bin/env python3
"""
Fix SQLAlchemy compatibility issue with Python 3.13
"""
import subprocess
import sys

def fix_sqlalchemy_python313():
    """Fix SQLAlchemy for Python 3.13"""
    print("🔧 Fixing SQLAlchemy for Python 3.13...")
    
    try:
        # Uninstall current SQLAlchemy
        print("Uninstalling current SQLAlchemy...")
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "sqlalchemy", "-y"], 
                      check=True, capture_output=True, text=True)
        
        # Install the latest development version that supports Python 3.13
        print("Installing SQLAlchemy 2.0.36 (Python 3.13 compatible)...")
        subprocess.run([sys.executable, "-m", "pip", "install", "sqlalchemy[asyncio]==2.0.36"], 
                      check=True, capture_output=True, text=True)
        
        # Test import
        print("Testing SQLAlchemy import...")
        import sqlalchemy
        from sqlalchemy import create_engine
        from sqlalchemy.ext.asyncio import create_async_engine
        
        print(f"✅ SQLAlchemy {sqlalchemy.__version__} installed and working!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install SQLAlchemy 2.0.36: {e}")
        print("Trying alternative approach...")
        
        # Try installing from git (latest development)
        try:
            print("Installing SQLAlchemy from git (latest development)...")
            subprocess.run([sys.executable, "-m", "pip", "install", "git+https://github.com/sqlalchemy/sqlalchemy.git"], 
                          check=True, capture_output=True, text=True)
            
            # Test import
            import sqlalchemy
            from sqlalchemy import create_engine
            from sqlalchemy.ext.asyncio import create_async_engine
            
            print(f"✅ SQLAlchemy {sqlalchemy.__version__} (development) installed and working!")
            return True
            
        except Exception as e2:
            print(f"❌ Git installation also failed: {e2}")
            return False
            
    except ImportError as e:
        print(f"❌ SQLAlchemy import still failing: {e}")
        return False

def downgrade_python_version():
    """Suggest downgrading Python version"""
    print("\n🔄 Alternative Solution: Downgrade Python Version")
    print("The SQLAlchemy typing issue is specific to Python 3.13.")
    print("Consider using Python 3.11 or 3.12 instead:")
    print("\n1. Install Python 3.11:")
    print("   sudo apt update")
    print("   sudo apt install python3.11 python3.11-venv python3.11-pip")
    print("\n2. Create new virtual environment:")
    print("   python3.11 -m venv venv311")
    print("   source venv311/bin/activate")
    print("\n3. Install dependencies:")
    print("   pip install -r requirements.txt")

if __name__ == "__main__":
    print("🐍 Python 3.13 SQLAlchemy Compatibility Fix")
    print("=" * 50)
    
    if fix_sqlalchemy_python313():
        print("\n🎉 SQLAlchemy fix completed successfully!")
        print("You can now run: python setup_vps.py")
    else:
        print("\n❌ SQLAlchemy fix failed.")
        print("This is a known issue with Python 3.13 and SQLAlchemy.")
        downgrade_python_version()
