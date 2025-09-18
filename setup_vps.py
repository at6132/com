#!/usr/bin/env python3
"""
VPS-Specific COM Environment Setup Script
Handles common VPS deployment issues and SQLAlchemy compatibility
"""
import os
import sys
import subprocess
import platform
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    print("🔍 Loading .env file...")
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv not available - .env file won't be loaded automatically")

def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def print_section(title):
    """Print a formatted section"""
    print(f"\n📋 {title}")
    print("-" * 40)

def check_python_version():
    """Check Python version compatibility"""
    print_section("Checking Python Version")
    
    version = sys.version_info
    print(f"Current Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major == 3 and version.minor >= 11:
        print("✅ Python version is compatible (3.11+)")
        return True
    else:
        print("❌ Python 3.11+ is required")
        print("Please upgrade your Python installation")
        return False

def fix_sqlalchemy_issue():
    """Fix SQLAlchemy typing compatibility issue"""
    print_section("Fixing SQLAlchemy Compatibility")
    
    try:
        print("Upgrading SQLAlchemy to fix typing issues...")
        
        # Uninstall current SQLAlchemy
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "sqlalchemy", "-y"], 
                      capture_output=True, text=True)
        
        # Install compatible version
        subprocess.run([sys.executable, "-m", "pip", "install", "sqlalchemy[asyncio]==2.0.25"], 
                      check=True, capture_output=True, text=True)
        
        print("✅ SQLAlchemy updated successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to update SQLAlchemy: {e}")
        return False

def install_dependencies_vps():
    """Install dependencies with VPS-specific fixes"""
    print_section("Installing Dependencies (VPS Optimized)")
    
    try:
        # First, upgrade pip
        print("Upgrading pip...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], 
                      check=True, capture_output=True, text=True)
        
        # Install dependencies in specific order to avoid conflicts
        packages = [
            "fastapi==0.104.1",
            "uvicorn[standard]==0.24.0",
            "pydantic==2.5.0",
            "pydantic-settings==2.1.0",
            "sqlalchemy[asyncio]==2.0.25",
            "alembic==1.13.1",
            "asyncpg==0.29.0",
            "redis[hiredis]==5.0.1",
            "httpx==0.25.2",
            "python-jose[cryptography]==3.3.0",
            "passlib[bcrypt]==1.7.4",
            "python-multipart==0.0.6",
            "python-dotenv==1.0.0",
            "pyyaml==6.0.1",
            "websockets==12.0",
            "gunicorn==21.2.0"
        ]
        
        for package in packages:
            print(f"Installing {package}...")
            subprocess.run([sys.executable, "-m", "pip", "install", package], 
                          check=True, capture_output=True, text=True)
        
        print("✅ All dependencies installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        print("Trying alternative installation method...")
        
        # Try installing from requirements.txt
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                          check=True, capture_output=True, text=True)
            print("✅ Dependencies installed from requirements.txt")
            return True
        except subprocess.CalledProcessError as e2:
            print(f"❌ Alternative installation also failed: {e2}")
            return False

def check_dependencies():
    """Check if required dependencies are installed"""
    print_section("Checking Dependencies")
    
    required_packages = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "sqlalchemy",
        "asyncpg",
        "redis",
        "alembic",
        "yaml",
        "bcrypt",
        "websockets"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - MISSING")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        return False
    else:
        print("\n✅ All required packages are installed")
        return True

def test_sqlalchemy_import():
    """Test SQLAlchemy import to verify fix"""
    print_section("Testing SQLAlchemy Import")
    
    try:
        import sqlalchemy
        from sqlalchemy import create_engine
        from sqlalchemy.ext.asyncio import create_async_engine
        print(f"✅ SQLAlchemy {sqlalchemy.__version__} imported successfully")
        print("✅ Async engine creation works")
        return True
    except Exception as e:
        print(f"❌ SQLAlchemy import failed: {e}")
        return False

def check_database():
    """Check database connectivity"""
    print_section("Checking Database")
    
    # Check if asyncpg is available
    try:
        import asyncpg
        print("✅ asyncpg package available")
    except ImportError:
        print("❌ asyncpg package not available")
        return False
    
    # Check environment variables
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print(f"✅ DATABASE_URL is set")
        # Mask password in output
        if '@' in db_url:
            masked_url = db_url.split('@')[0].split('://')[0] + '://***@' + db_url.split('@')[1]
            print(f"   Database: {masked_url}")
        else:
            print(f"   Database: {db_url}")
    else:
        print("❌ DATABASE_URL not set")
        print("Please set DATABASE_URL environment variable")
        return False
    
    return True

def check_redis():
    """Check Redis connectivity"""
    print_section("Checking Redis")
    
    # Check if redis package is available
    try:
        import redis.asyncio
        print("✅ redis package available")
    except ImportError:
        print("❌ redis package not available")
        return False
    
    # Check environment variables
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        print(f"✅ REDIS_URL is set")
        if '@' in redis_url:
            print(f"   Redis: {redis_url.split('@')[-1]}")
        else:
            print(f"   Redis: {redis_url}")
    else:
        print("❌ REDIS_URL not set")
        print("Please set REDIS_URL environment variable")
        return False
    
    return True

def create_env_file():
    """Create .env file with VPS template values"""
    print_section("Creating Environment File")
    
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    # Create VPS-optimized .env file
    env_template = """# COM Environment Configuration - VPS Optimized
# Update these values with your actual VPS configuration

# Database Configuration
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/com_database

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=false
PRODUCTION=true

# Security
SECRET_KEY=your-secret-key-here-change-this
API_KEY_SALT=your-api-key-salt-here-change-this

# Broker Configuration
BROKER_CONFIG_PATH=config/brokers

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# VPS Specific
WORKERS=4
MAX_REQUESTS=1000
TIMEOUT=30
"""
    
    try:
        with open(env_file, "w") as f:
            f.write(env_template)
        print("✅ .env file created with VPS template values")
        print("⚠️  IMPORTANT: Update the values with your actual VPS configuration")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False

def run_database_migration():
    """Run database migrations"""
    print_section("Running Database Migrations")
    
    try:
        print("Running Alembic migrations...")
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], 
                              check=True, capture_output=True, text=True)
        print("✅ Database migrations completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Database migration failed: {e}")
        print("Please ensure your database is running and accessible")
        return False

def print_vps_next_steps():
    """Print VPS-specific next steps"""
    print_header("VPS Setup Next Steps")
    
    print("🎯 To complete your VPS COM system setup:")
    print("\n1. 📝 Update your .env file with VPS values:")
    print("   - Set DATABASE_URL to your PostgreSQL connection string")
    print("   - Set REDIS_URL to your Redis connection string")
    print("   - Update SECRET_KEY and API_KEY_SALT with secure random values")
    print("   - Set PRODUCTION=true for production deployment")
    
    print("\n2. 🗄️  Ensure your database is running:")
    print("   - PostgreSQL should be accessible at your DATABASE_URL")
    print("   - Database 'com_database' should exist")
    print("   - Run: sudo systemctl status postgresql")
    
    print("\n3. 🔴 Ensure Redis is running:")
    print("   - Redis should be accessible at your REDIS_URL")
    print("   - Run: sudo systemctl status redis")
    
    print("\n4. 🏦 Configure your broker:")
    print("   - Update config/brokers/mexc.yaml with your MEXC token")
    
    print("\n5. 🚀 Start the system:")
    print("   - Development: python start_com_system.py")
    print("   - Production: gunicorn com.app.main:app -w 4 -k uvicorn.workers.UvicornWorker")
    
    print("\n6. 🧪 Test the system:")
    print("   - Check API docs at: http://your-vps-ip:8000/docs")
    print("   - Test WebSocket at: ws://your-vps-ip:8000/api/v1/stream")
    
    print("\n7. 🔒 Security considerations:")
    print("   - Configure firewall rules")
    print("   - Use HTTPS in production")
    print("   - Set up SSL certificates")
    print("   - Consider using a reverse proxy (nginx)")

def main():
    """Main VPS setup function"""
    print_header("COM VPS Environment Setup")
    print("This script will help you configure your COM system for VPS deployment")
    
    # Check Python version
    if not check_python_version():
        return 1
    
    # Fix SQLAlchemy issue first
    if not fix_sqlalchemy_issue():
        print("⚠️  SQLAlchemy fix failed, continuing with installation...")
    
    # Install dependencies
    if not install_dependencies_vps():
        print("❌ Failed to install dependencies")
        return 1
    
    # Test SQLAlchemy import
    if not test_sqlalchemy_import():
        print("❌ SQLAlchemy still has issues, trying alternative fix...")
        # Try one more time
        fix_sqlalchemy_issue()
        if not test_sqlalchemy_import():
            print("❌ SQLAlchemy issues persist. Please check your Python version.")
            return 1
    
    # Check dependencies
    if not check_dependencies():
        print("❌ Some dependencies are missing")
        return 1
    
    # Create environment file
    create_env_file()
    
    # Check database
    if not check_database():
        print("\nPlease configure your database connection and try again")
        return 1
    
    # Check Redis
    if not check_redis():
        print("\nPlease configure your Redis connection and try again")
        return 1
    
    # Run migrations
    print("\nWould you like to run database migrations now? (y/n): ", end="")
    try:
        response = input().lower().strip()
        if response in ['y', 'yes']:
            if not run_database_migration():
                print("\nMigrations failed. Please check your database connection.")
                return 1
    except KeyboardInterrupt:
        print("\nSkipping migrations")
    
    # Print next steps
    print_vps_next_steps()
    
    print_header("VPS Setup Complete!")
    print("Your COM system is now configured for VPS deployment.")
    print("Follow the next steps above to complete your setup.")
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nSetup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nSetup failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
