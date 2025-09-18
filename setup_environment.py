#!/usr/bin/env python3
"""
COM Environment Setup Script
Helps configure environment variables and dependencies for the COM system
"""
import os
import sys
import subprocess
import platform
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    print("🔍 DEBUG: Loading .env file...")
    result = load_dotenv()
    print(f"🔍 DEBUG: load_dotenv() result: {result}")
    
    # Debug: Check if .env file exists
    env_file = Path(".env")
    if env_file.exists():
        print(f"🔍 DEBUG: .env file exists at: {env_file.absolute()}")
        print(f"🔍 DEBUG: .env file size: {env_file.stat().st_size} bytes")
        
        # Show first few lines of .env file
        try:
            with open(env_file, 'r') as f:
                lines = f.readlines()[:5]  # First 5 lines
                print("🔍 DEBUG: First 5 lines of .env file:")
                for i, line in enumerate(lines, 1):
                    print(f"   {i}: {line.strip()}")
        except Exception as e:
            print(f"🔍 DEBUG: Error reading .env file: {e}")
    else:
        print("🔍 DEBUG: .env file does not exist")
        
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
        "yaml",  # pyyaml package imports as yaml
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

def install_dependencies():
    """Install missing dependencies"""
    print_section("Installing Dependencies")
    
    try:
        print("Installing packages from requirements.txt...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True, capture_output=True, text=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def check_database():
    """Check database connectivity"""
    print_section("Checking Database")
    
    # Debug: Show all environment variables
    print("🔍 DEBUG: All environment variables:")
    for key, value in os.environ.items():
        if 'DATABASE' in key or 'DB_' in key:
            print(f"   {key}: {value}")
    
    # Check if asyncpg is available
    try:
        import asyncpg
        print("✅ asyncpg package available")
    except ImportError:
        print("❌ asyncpg package not available")
        return False
    
    # Check environment variables
    db_url = os.getenv("DATABASE_URL")
    print(f"🔍 DEBUG: DATABASE_URL from os.getenv(): {db_url}")
    
    if db_url:
        print(f"✅ DATABASE_URL is set: {db_url}")
        if '@' in db_url:
            print(f"   Parsed as: {db_url.split('@')[-1]}")
        else:
            print(f"   Full URL: {db_url}")
    else:
        print("❌ DATABASE_URL not set")
        print("Please set DATABASE_URL environment variable")
        return False
    
    return True

def check_redis():
    """Check Redis connectivity"""
    print_section("Checking Redis")
    
    # Debug: Show Redis environment variables
    print("🔍 DEBUG: Redis environment variables:")
    for key, value in os.environ.items():
        if 'REDIS' in key:
            print(f"   {key}: {value}")
    
    # Check if redis package is available
    try:
        import redis.asyncio
        print("✅ redis package available")
    except ImportError:
        print("❌ redis package not available")
        return False
    
    # Check environment variables
    redis_url = os.getenv("REDIS_URL")
    print(f"🔍 DEBUG: REDIS_URL from os.getenv(): {redis_url}")
    
    if redis_url:
        print(f"✅ REDIS_URL is set: {redis_url}")
        if '@' in redis_url:
            print(f"   Parsed as: {redis_url.split('@')[-1]}")
        else:
            print(f"   Full URL: {redis_url}")
    else:
        print("❌ REDIS_URL not set")
        print("Please set REDIS_URL environment variable")
        return False
    
    return True

def create_env_file():
    """Create .env file with template values"""
    print_section("Creating Environment File")
    
    env_file = Path(".env")
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    # Create template .env file
    env_template = """# COM Environment Configuration
# Copy this file to .env and update with your actual values

# Database Configuration
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/com_database

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=true
PRODUCTION=false

# Security
SECRET_KEY=your-secret-key-here
API_KEY_SALT=your-api-key-salt-here

# Broker Configuration
BROKER_CONFIG_PATH=config/brokers

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
"""
    
    try:
        with open(env_file, "w") as f:
            f.write(env_template)
        print("✅ .env file created with template values")
        print("Please update the values with your actual configuration")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False

def check_broker_config():
    """Check broker configuration files"""
    print_section("Checking Broker Configuration")
    
    config_path = Path("config/brokers")
    if not config_path.exists():
        print("❌ Broker config directory not found")
        print("Creating broker config directory...")
        config_path.mkdir(parents=True, exist_ok=True)
    
    mexc_config = config_path / "mexc.yaml"
    if not mexc_config.exists():
        print("❌ MEXC configuration file not found")
        print("Please create config/brokers/mexc.yaml with your MEXC settings")
        return False
    
    print("✅ Broker configuration directory exists")
    print(f"✅ MEXC config file found: {mexc_config}")
    
    # Check if MEXC config has token
    try:
        import yaml
        with open(mexc_config, 'r') as f:
            config = yaml.safe_load(f)
        
        if config.get('token'):
            print("✅ MEXC token is configured")
        else:
            print("⚠️  MEXC token not configured")
            print("Please add your MEXC token to the configuration file")
            return False
            
    except Exception as e:
        print(f"❌ Failed to read MEXC config: {e}")
        return False
    
    return True

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

def check_system_requirements():
    """Check system requirements"""
    print_section("System Requirements")
    
    # Check OS
    os_name = platform.system()
    print(f"Operating System: {os_name}")
    
    if os_name in ["Windows", "Linux", "Darwin"]:
        print("✅ Operating system is supported")
    else:
        print("⚠️  Operating system may have compatibility issues")
    
    # Check available memory
    try:
        import psutil
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)
        print(f"Available Memory: {memory_gb:.1f} GB")
        
        if memory_gb >= 2.0:
            print("✅ Sufficient memory available")
        else:
            print("⚠️  Low memory - consider closing other applications")
    except ImportError:
        print("⚠️  psutil not available - cannot check memory")
    
    return True

def print_next_steps():
    """Print next steps for the user"""
    print_header("Next Steps")
    
    print("🎯 To complete your COM system setup:")
    print("\n1. 📝 Update your .env file with actual values:")
    print("   - Set DATABASE_URL to your PostgreSQL connection string")
    print("   - Set REDIS_URL to your Redis connection string")
    print("   - Update SECRET_KEY and API_KEY_SALT with secure values")
    
    print("\n2. 🗄️  Ensure your database is running:")
    print("   - PostgreSQL should be accessible at your DATABASE_URL")
    print("   - Database 'com_database' should exist")
    
    print("\n3. 🔴 Ensure Redis is running:")
    print("   - Redis should be accessible at your REDIS_URL")
    
    print("\n4. 🏦 Configure your broker:")
    print("   - Update config/brokers/mexc.yaml with your MEXC token")
    print("   - Test broker connection with: python test_mexc_symbol_specific.py")
    
    print("\n5. 🚀 Start the system:")
    print("   - Run: python start_com_system.py")
    print("   - Or use: make start")
    
    print("\n6. 🧪 Test the system:")
    print("   - Run: python test_com_complete.py")
    print("   - Check API docs at: http://localhost:8000/docs")
    
    print("\n📚 For more information, see README.md")

def main():
    """Main setup function"""
    print_header("COM Environment Setup")
    print("This script will help you configure your COM system environment")
    
    # Debug: Show current working directory and environment
    print("🔍 DEBUG: Current working directory:", os.getcwd())
    print("🔍 DEBUG: Python executable:", sys.executable)
    print("🔍 DEBUG: Environment variables loaded:", len([k for k in os.environ.keys() if k.startswith(('DATABASE', 'REDIS', 'MEXC', 'SECURITY', 'RISK', 'LOG'))]))
    
    # Check Python version
    if not check_python_version():
        return 1
    
    # Check dependencies
    if not check_dependencies():
        print("\nInstalling missing dependencies...")
        if not install_dependencies():
            return 1
    
    # Check system requirements
    check_system_requirements()
    
    # Create environment file first
    create_env_file()
    
    # Debug: Show environment after .env loading
    print("🔍 DEBUG: Environment after .env loading:")
    for key, value in os.environ.items():
        if any(prefix in key for prefix in ['DATABASE', 'REDIS', 'MEXC', 'SECURITY', 'RISK', 'LOG']):
            print(f"   {key}: {value}")
    
    # Check database
    if not check_database():
        print("\nPlease configure your database connection and try again")
        return 1
    
    # Check Redis
    if not check_redis():
        print("\nPlease configure your Redis connection and try again")
        return 1
    
    # Check broker config
    if not check_broker_config():
        print("\nPlease configure your broker settings and try again")
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
    print_next_steps()
    
    print_header("Setup Complete!")
    print("Your COM system environment is now configured.")
    print("Follow the next steps above to start using your system.")
    
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
        sys.exit(1)
