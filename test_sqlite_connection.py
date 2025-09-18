#!/usr/bin/env python3
"""
Test script to verify SQLite database connection works
"""
import asyncio
import aiosqlite
import os

async def test_sqlite_connection():
    """Test SQLite connection"""
    print("🧪 Testing SQLite Database Connection")
    print("=" * 50)
    
    try:
        # Hardcoded SQLite configuration
        db_url = "sqlite+aiosqlite:///./com_database.db"
        print(f"📊 Database URL: {db_url}")
        
        # Extract the file path from the URL
        db_path = "./com_database.db"
        print(f"📁 Database file: {db_path}")
        
        # Test basic SQLite connection
        print("\n🔌 Testing basic SQLite connection...")
        async with aiosqlite.connect(db_path) as db:
            print("✅ SQLite connection successful!")
            
            # Test creating a table
            print("\n📋 Testing table creation...")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS test_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✅ Table creation successful!")
            
            # Test inserting data
            print("\n📝 Testing data insertion...")
            await db.execute("INSERT INTO test_table (name) VALUES (?)", ("test_name",))
            print("✅ Data insertion successful!")
            
            # Test querying data
            print("\n🔍 Testing data query...")
            async with db.execute("SELECT * FROM test_table") as cursor:
                rows = await cursor.fetchall()
                print(f"✅ Query successful! Found {len(rows)} rows")
                for row in rows:
                    print(f"   Row: {row}")
            
            await db.commit()
            print("\n✅ All SQLite tests passed!")
            return True
            
    except Exception as e:
        print(f"❌ SQLite test failed: {e}")
        return False

async def test_asyncpg_fallback():
    """Test if asyncpg still works (for when we switch back to PostgreSQL)"""
    print("\n🔄 Testing asyncpg package...")
    try:
        import asyncpg
        print("✅ asyncpg package is available")
        return True
    except ImportError:
        print("❌ asyncpg package not available")
        return False

async def main():
    """Main test function"""
    print("🚀 COM System Database Connection Test")
    print("=" * 60)
    
    # Test SQLite
    sqlite_works = await test_sqlite_connection()
    
    # Test asyncpg availability
    asyncpg_works = await test_asyncpg_fallback()
    
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"SQLite Connection: {'✅ WORKING' if sqlite_works else '❌ FAILED'}")
    print(f"asyncpg Package: {'✅ AVAILABLE' if asyncpg_works else '❌ MISSING'}")
    
    if sqlite_works:
        print("\n🎉 SQLite is working! You can now:")
        print("1. Update your .env file to use SQLite")
        print("2. Run the setup script: python3 setup_environment.py")
        print("3. Start the COM system")
    else:
        print("\n⚠️ SQLite test failed. Please check the error above.")
    
    return sqlite_works

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 Test script crashed: {e}")
        exit(1)
