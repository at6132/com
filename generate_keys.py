#!/usr/bin/env python3
"""
ATQ Ventures COM - Key Generation Utility
Generate secure API keys and security keys for authentication
"""

import secrets
import hashlib
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

class KeyGenerator:
    def __init__(self):
        self.keys_dir = "keys"
        self.ensure_keys_directory()
    
    def ensure_keys_directory(self):
        """Create keys directory if it doesn't exist"""
        if not os.path.exists(self.keys_dir):
            os.makedirs(self.keys_dir)
            print(f"✅ Created keys directory: {self.keys_dir}")
    
    def generate_api_key(self, strategy_name: str = None) -> str:
        """Generate a secure API key"""
        # Generate random bytes
        random_bytes = secrets.token_bytes(32)
        
        # Create timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create strategy identifier
        strategy_id = strategy_name or "default"
        
        # Combine and hash
        combined = f"{strategy_id}_{timestamp}".encode() + random_bytes
        api_key = base64.urlsafe_b64encode(combined).decode('utf-8')
        
        # Truncate to reasonable length (remove padding)
        api_key = api_key.rstrip('=')
        
        return api_key
    
    def generate_secret_key(self) -> str:
        """Generate a secure secret key for HMAC signing"""
        # Generate 64 random bytes for high security
        random_bytes = secrets.token_bytes(64)
        
        # Encode as base64
        secret_key = base64.urlsafe_b64encode(random_bytes).decode('utf-8')
        
        # Remove padding
        secret_key = secret_key.rstrip('=')
        
        return secret_key
    
    def generate_salt(self) -> str:
        """Generate a salt for additional security"""
        # Generate 32 random bytes
        random_bytes = secrets.token_bytes(32)
        
        # Encode as base64
        salt = base64.urlsafe_b64encode(random_bytes).decode('utf-8')
        
        # Remove padding
        salt = salt.rstrip('=')
        
        return salt
    
    def generate_key_pair(self, strategy_name: str = None) -> dict:
        """Generate a complete key pair for a strategy"""
        api_key = self.generate_api_key(strategy_name)
        secret_key = self.generate_secret_key()
        salt = self.generate_salt()
        
        key_pair = {
            "strategy_name": strategy_name or "default",
            "api_key": api_key,
            "secret_key": secret_key,
            "salt": salt,
            "created_at": datetime.now().isoformat(),
            "description": f"API keys for {strategy_name or 'default'} strategy"
        }
        
        return key_pair
    
    async def add_key_to_database(self, key_pair: dict) -> bool:
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
    
    def save_key_pair(self, key_pair: dict, filename: str = None):
        """Save key pair to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            strategy = key_pair["strategy_name"].replace(" ", "_")
            filename = f"{strategy}_{timestamp}_keys.json"
        
        filepath = os.path.join(self.keys_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(key_pair, f, indent=2)
        
        print(f"✅ Saved key pair to: {filepath}")
        return filepath
    
    def load_key_pair(self, filepath: str) -> dict:
        """Load key pair from file"""
        with open(filepath, 'r') as f:
            key_pair = json.load(f)
        
        return key_pair
    
    def list_key_files(self) -> list:
        """List all key files in the keys directory"""
        if not os.path.exists(self.keys_dir):
            return []
        
        key_files = []
        for filename in os.listdir(self.keys_dir):
            if filename.endswith('_keys.json'):
                filepath = os.path.join(self.keys_dir, filename)
                key_files.append(filepath)
        
        return key_files
    
    async def generate_multiple_keys(self, strategies: list):
        """Generate keys for multiple strategies"""
        print(f"🔑 Generating keys for {len(strategies)} strategies...")
        
        all_keys = {}
        
        for strategy in strategies:
            print(f"\n📋 Generating keys for: {strategy}")
            key_pair = self.generate_key_pair(strategy)
            
            # Save individual file
            filename = f"{strategy.replace(' ', '_')}_keys.json"
            self.save_key_pair(key_pair, filename)
            
            # Add to database
            await self.add_key_to_database(key_pair)
            
            # Add to all keys
            all_keys[strategy] = key_pair
        
        # Save combined file
        combined_filename = f"all_strategies_{datetime.now().strftime('%Y%m%d_%H%M%S')}_keys.json"
        combined_filepath = os.path.join(self.keys_dir, combined_filename)
        
        with open(combined_filepath, 'w') as f:
            json.dump(all_keys, f, indent=2)
        
        print(f"\n✅ Saved combined keys to: {combined_filepath}")
        return all_keys
    
    def create_env_template(self, key_pair: dict):
        """Create .env template with the generated keys"""
        env_content = f"""# ATQ Ventures COM - Environment Configuration
# Generated on: {datetime.now().isoformat()}

# API Authentication
API_KEY_ID={key_pair['api_key']}
API_KEY_SECRET={key_pair['secret_key']}
API_KEY_SALT={key_pair['salt']}

# Security
SECURITY_SECRET_KEY={key_pair['secret_key']}

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
        
        env_filepath = os.path.join(self.keys_dir, f"{key_pair['strategy_name']}_env_template.env")
        
        with open(env_filepath, 'w') as f:
            f.write(env_content)
        
        print(f"✅ Created .env template: {env_filepath}")
        return env_filepath
    
    def display_key_info(self, key_pair: dict):
        """Display key information in a formatted way"""
        print("\n" + "="*60)
        print("🔑 GENERATED KEY PAIR")
        print("="*60)
        print(f"Strategy: {key_pair['strategy_name']}")
        print(f"Created: {key_pair['created_at']}")
        print(f"Description: {key_pair['description']}")
        print("-"*60)
        print("API Key (for X-API-Key header):")
        print(f"  {key_pair['api_key']}")
        print("-"*60)
        print("Secret Key (for HMAC signing):")
        print(f"  {key_pair['secret_key']}")
        print("-"*60)
        print("Salt (additional security):")
        print(f"  {key_pair['salt']}")
        print("="*60)
        print("\n⚠️  IMPORTANT SECURITY NOTES:")
        print("• Keep these keys secure and never share them")
        print("• Use different keys for different environments")
        print("• Rotate keys regularly for production use")
        print("• Store keys securely (not in version control)")
        print("="*60)

async def main():
    """Main function for interactive key generation"""
    print("🔑 ATQ Ventures COM - Key Generation Utility")
    print("="*50)
    
    if not DB_AVAILABLE:
        print("⚠️  Database integration not available")
        print("   Install required packages: pip install aiosqlite sqlalchemy")
        print("   Keys will only be saved to files")
    
    generator = KeyGenerator()
    
    while True:
        print("\nOptions:")
        print("1. Generate single key pair")
        print("2. Generate keys for multiple strategies")
        print("3. List existing key files")
        print("4. Load and display existing keys")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == "1":
            strategy_name = input("Enter strategy name (or press Enter for 'default'): ").strip()
            if not strategy_name:
                strategy_name = "default"
            
            key_pair = generator.generate_key_pair(strategy_name)
            generator.display_key_info(key_pair)
            
            # Save keys
            save_choice = input("\nSave keys to file? (y/n): ").strip().lower()
            if save_choice in ['y', 'yes']:
                filename = input("Enter filename (or press Enter for auto-generated): ").strip()
                if not filename:
                    filename = None
                
                filepath = generator.save_key_pair(key_pair, filename)
                
                # Add to database
                if DB_AVAILABLE:
                    db_choice = input("Add key to COM database? (y/n): ").strip().lower()
                    if db_choice in ['y', 'yes']:
                        await generator.add_key_to_database(key_pair)
                
                # Create .env template
                env_choice = input("Create .env template? (y/n): ").strip().lower()
                if env_choice in ['y', 'yes']:
                    generator.create_env_template(key_pair)
        
        elif choice == "2":
            print("\nEnter strategy names (one per line, empty line to finish):")
            strategies = []
            while True:
                strategy = input("Strategy name: ").strip()
                if not strategy:
                    break
                strategies.append(strategy)
            
            if strategies:
                await generator.generate_multiple_keys(strategies)
            else:
                print("No strategies entered.")
        
        elif choice == "3":
            key_files = generator.list_key_files()
            if key_files:
                print(f"\nFound {len(key_files)} key files:")
                for filepath in key_files:
                    print(f"  {os.path.basename(filepath)}")
            else:
                print("\nNo key files found.")
        
        elif choice == "4":
            key_files = generator.list_key_files()
            if not key_files:
                print("No key files found.")
                continue
            
            print(f"\nAvailable key files:")
            for i, filepath in enumerate(key_files):
                print(f"  {i+1}. {os.path.basename(filepath)}")
            
            try:
                file_choice = int(input("\nSelect file number: ")) - 1
                if 0 <= file_choice < len(key_files):
                    key_pair = generator.load_key_pair(key_files[file_choice])
                    generator.display_key_info(key_pair)
                else:
                    print("Invalid selection.")
            except ValueError:
                print("Invalid input.")
        
        elif choice == "5":
            print("\n👋 Goodbye!")
            break
        
        else:
            print("Invalid option. Please select 1-5.")

if __name__ == "__main__":
    asyncio.run(main())
