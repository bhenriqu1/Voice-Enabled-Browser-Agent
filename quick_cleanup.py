#!/usr/bin/env python3
"""
Quick cleanup script to force delete any active Browserbase sessions
"""
import asyncio
import aiohttp
from config import settings

async def force_cleanup():
    """Force cleanup of any active sessions"""
    print("🧹 Force cleaning up Browserbase sessions...")
    
    api_key = settings.browserbase_api_key
    base_url = "https://api.browserbase.com/v1"
    
    async with aiohttp.ClientSession(
        headers={"X-BB-API-Key": api_key}
    ) as session:
        try:
            # List all sessions
            print("🔄 Listing active sessions...")
            async with session.get(f"{base_url}/sessions") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Handle different response formats
                    if isinstance(data, dict):
                        sessions = data.get('data', data.get('sessions', []))
                    elif isinstance(data, list):
                        sessions = data
                    else:
                        sessions = []
                    
                    print(f"Found {len(sessions)} sessions")
                    
                    # Delete each session
                    for sess in sessions:
                        if isinstance(sess, dict):
                            session_id = sess.get('id')
                            status = sess.get('status', 'unknown')
                        else:
                            session_id = str(sess)
                            status = 'unknown'
                        
                        print(f"Deleting session: {session_id} (status: {status})")
                        
                        async with session.delete(f"{base_url}/sessions/{session_id}") as delete_resp:
                            if delete_resp.status in (200, 204, 404):
                                print(f"✅ Deleted {session_id}")
                            else:
                                text = await delete_resp.text()
                                print(f"⚠️ Failed to delete {session_id}: {delete_resp.status}")
                else:
                    print(f"⚠️ Could not list sessions: {resp.status}")
                    text = await resp.text()
                    print(f"Response: {text}")
                    
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("✅ Cleanup completed!")

if __name__ == "__main__":
    asyncio.run(force_cleanup())
