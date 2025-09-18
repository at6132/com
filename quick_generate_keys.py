#!/usr/bin/env python3
"""
Quick Key Generation for ATQ Ventures COM
Generate keys immediately without interactive menu
"""

import secrets
import base64
import json
import bcrypt
import asyncio
from datetime import datetime
import os
import sys

# Add COM app to path for database access
sys.path.append(os.path.join(os.path.dirname(__file__), 'com'))

try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from com.app.core.database import ApiKey, init_db
    from com.app.config import get_settings
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("⚠️  Database integration not available - keys will only be saved to files")

async def add_key_to_database(key_pair: dict) -> bool:
    """Add the generated key to the COM database"""
    if not DB_AVAILABLE:
        print("⚠️  Database not available - skipping database insertion")
        return False
    
    try:
        # Get database settings
        settings = get_settings()
        database_url = settings.database_url
        
        print(f"🔗 Adding key to database: {database_url}")
        
        # Create engine
        engine = create_async_engine(database_url, echo=False)
        
        try:
            # Initialize database (create tables if they don't exist)
            async with engine.begin() as conn:
                await init_db()
            
            # Create session
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session() as session:
                # Check if API key already exists
                result = await session.execute(
                    select(ApiKey).where(ApiKey.key_id == key_pair['api_key'])
                )
                existing_key = result.scalar_one_or_none()
                
                if existing_key:
                    print(f"🔄 API key already exists, updating...")
                    
                    # Update existing key
                    existing_key.secret_key = key_pair['secret_key']
                    existing_key.secret_hash = bcrypt.hashpw(key_pair['secret_key'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    existing_key.name = f"{key_pair['strategy_name']} Strategy"
                    existing_key.owner = key_pair['strategy_name']
                    existing_key.permissions = json.dumps(["orders:create", "orders:read", "positions:read"])
                    existing_key.is_active = True
                    
                else:
                    print(f"🆕 Creating new API key in database...")
                    
                    # Create new API key
                    new_api_key = ApiKey(
                        key_id=key_pair['api_key'],
                        name=f"{key_pair['strategy_name']} Strategy",
                        owner=key_pair['strategy_name'],
                        permissions=json.dumps(["orders:create", "orders:read", "positions:read"]),
                        secret_key=key_pair['secret_key'],
                        secret_hash=bcrypt.hashpw(key_pair['secret_key'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                        is_active=True,
                        rate_limit_per_minute=1000,
                        rate_limit_per_hour=10000
                    )
                    
                    session.add(new_api_key)
                
                # Commit changes
                await session.commit()
                print("✅ API key added to database successfully!")
                
                return True
                
        except Exception as e:
            print(f"❌ Database error: {e}")
            return False
            
        finally:
            await engine.dispose()
            
    except Exception as e:
        print(f"❌ Failed to add key to database: {e}")
        return False

async def generate_keys(strategy_name="test_strategy"):
    """Quickly generate API keys for immediate use"""
    
    # Create keys directory
    if not os.path.exists("keys"):
        os.makedirs("keys")
        print("✅ Created keys directory")
    
    # Generate API key
    random_bytes = secrets.token_bytes(32)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined = f"{strategy_name}_{timestamp}".encode() + random_bytes
    api_key = base64.urlsafe_b64encode(combined).decode('utf-8').rstrip('=')
    
    # Generate secret key
    secret_key = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode('utf-8').rstrip('=')
    
    # Generate salt
    salt = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    
    # Create key pair
    key_pair = {
        "strategy_name": strategy_name,
        "api_key": api_key,
        "secret_key": secret_key,
        "salt": salt,
        "created_at": datetime.now().isoformat()
    }
    
    # Save to file
    filename = f"{strategy_name}_keys.json"
    filepath = os.path.join("keys", filename)
    
    with open(filepath, 'w') as f:
        json.dump(key_pair, f, indent=2)
    
    print(f"✅ Generated keys for: {strategy_name}")
    print(f"✅ Saved to: {filepath}")
    
    # Add to database
    await add_key_to_database(key_pair)
    
    # Display keys
    print("\n" + "="*60)
    print("🔑 GENERATED KEYS")
    print("="*60)
    print(f"Strategy: {strategy_name}")
    print(f"API Key: {api_key}")
    print(f"Secret Key: {secret_key}")
    print(f"Salt: {salt}")
    print("="*60)
    
    # Create .env template
    env_content = f"""# ATQ Ventures COM - Environment Configuration
# Generated on: {datetime.now().isoformat()}

# API Authentication
API_KEY_ID={api_key}
API_KEY_SECRET={secret_key}
API_KEY_SALT={salt}

# Security
SECURITY_SECRET_KEY={secret_key}

# COM Server Configuration
COM_SERVER_URL=http://localhost:8000
COM_SERVER_PORT=8000

# Database (SQLite for development)
DATABASE_URL=sqlite+aiosqlite:///./com_database.db

# Redis
REDIS_URL=redis://localhost:6379/0

# MEXC Configuration
MEXC_API_KEY=your_mexc_api_key_here
MEXC_SECRET_KEY=your_mexc_secret_key_here
MEXC_SANDBOX=true

# Environment
ENVIRONMENT=development
DEBUG=true
"""
    
    env_filename = f"{strategy_name}_env_template.env"
    env_filepath = os.path.join("keys", env_filename)
    
    with open(env_filepath, 'w') as f:
        f.write(env_content)
    
    print(f"✅ Created .env template: {env_filepath}")
    
    return key_pair

async def main():
    """Main function"""
    if not DB_AVAILABLE:
        print("⚠️  Database integration not available")
        print("   Install required packages: pip install aiosqlite sqlalchemy")
        print("   Keys will only be saved to files")
    
    # Generate keys for test strategy
    keys = await generate_keys("test_strategy")
    
    print("\n📋 Next steps:")
    print("1. Copy the API Key and Secret Key to your GUI configuration")
    print("2. Use the .env template to update your environment file")
    print("3. Test the authentication in your GUI")
    
    if DB_AVAILABLE:
        print("4. ✅ Keys are already in the COM database - ready to test!")

if __name__ == "__main__":
    asyncio.run(main())
