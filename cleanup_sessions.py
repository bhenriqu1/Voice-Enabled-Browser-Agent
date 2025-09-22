#!/usr/bin/env python3
"""
Cleanup script to remove any existing Browserbase sessions
"""
import asyncio
import json
import os
import aiohttp
from config import settings

async def cleanup_sessions():
    """Clean up any existing Browserbase sessions"""
    print("🧹 Cleaning up existing Browserbase sessions...")
    
    api_key = settings.browserbase_api_key
    base_url = "https://api.browserbase.com/v1"
    
    # Check for existing session metadata
    session_file = getattr(settings, "browser_state_path", ".bb_session.json")
    if os.path.exists(session_file):
        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)
                session_id = session_data.get('id')
                if session_id:
                    print(f"Found existing session: {session_id}")
                    
                    async with aiohttp.ClientSession(
                        headers={"X-BB-API-Key": api_key}
                    ) as session:
                        # Delete the session
                        url = f"{base_url}/sessions/{session_id}"
                        async with session.delete(url) as resp:
                            if resp.status in (200, 204, 404):
                                print(f"✅ Cleaned up session: {session_id}")
                            else:
                                text = await resp.text()
                                print(f"⚠️ Could not clean up session {session_id}: {resp.status} - {text}")
                    
                    # Remove the session file
                    os.remove(session_file)
                    print("✅ Removed session metadata file")
                else:
                    print("No session ID found in metadata file")
        except Exception as e:
            print(f"⚠️ Error reading session file: {e}")
            try:
                os.remove(session_file)
                print("✅ Removed corrupted session file")
            except:
                pass
    else:
        print("No existing session metadata found")
    
    # Try to list and clean up any active sessions
    try:
        async with aiohttp.ClientSession(
            headers={"X-BB-API-Key": api_key}
        ) as session:
            # List sessions
            url = f"{base_url}/sessions"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sessions = data.get('data', [])
                    if sessions:
                        print(f"Found {len(sessions)} active sessions:")
                        for sess in sessions:
                            session_id = sess.get('id')
                            status = sess.get('status', 'unknown')
                            print(f"  - {session_id} (status: {status})")
                            
                            # Try to delete each session
                            delete_url = f"{base_url}/sessions/{session_id}"
                            async with session.delete(delete_url) as delete_resp:
                                if delete_resp.status in (200, 204, 404):
                                    print(f"    ✅ Deleted session {session_id}")
                                else:
                                    text = await delete_resp.text()
                                    print(f"    ⚠️ Could not delete {session_id}: {delete_resp.status} - {text}")
                    else:
                        print("No active sessions found")
                else:
                    text = await resp.text()
                    print(f"⚠️ Could not list sessions: {resp.status} - {text}")
    except Exception as e:
        print(f"⚠️ Error during session cleanup: {e}")
    
    print("🧹 Cleanup completed!")

if __name__ == "__main__":
    asyncio.run(cleanup_sessions())
