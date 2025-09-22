"""
Demo script for the Voice-Enabled Browser Agent
"""
import asyncio
import logging
from voice_browser_agent import VoiceBrowserAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_voice_commands():
    """Demo various voice commands"""
    agent = VoiceBrowserAgent()
    
    try:
        # Initialize agent
        if not await agent.initialize():
            print("Failed to initialize agent")
            return
        
        print("🎤 Voice Browser Agent Demo")
        print("=" * 50)
        print("This demo will simulate voice commands and show the agent's capabilities.")
        print("In a real scenario, you would speak these commands.")
        print()
        
        # Demo commands
        demo_commands = [
            "Go to Google",
            "Search for Python tutorials",
            "Click on the first search result",
            "Take a screenshot",
            "Extract all the links from this page",
            "Navigate to GitHub and search for machine learning repositories",
            "Fill out a contact form with my name and email",
            "Scroll down to see more results",
            "Download the first PDF file you find"
        ]
        
        for i, command in enumerate(demo_commands, 1):
            print(f"\n🎯 Demo Command {i}: '{command}'")
            print("-" * 40)
            
            # Process the command
            await agent.process_voice_input(command)
            
            # Wait a bit between commands
            await asyncio.sleep(2)
        
        print("\n✅ Demo completed!")
        
        # Show session stats
        stats = await agent.get_session_stats()
        print(f"\n📊 Session Statistics:")
        print(f"   - Conversation turns: {stats.get('conversation_turns', 0)}")
        print(f"   - Redis cache items: {stats.get('redis_stats', {}).get('total_keys', 0)}")
        print(f"   - Memory entries: {stats.get('memory_stats', {}).get('total_memories', 0)}")
    
    except Exception as e:
        logger.error(f"Demo error: {e}")
    
    finally:
        await agent.cleanup()


async def demo_workflow():
    """Demo a complex multi-step workflow"""
    agent = VoiceBrowserAgent()
    
    try:
        if not await agent.initialize():
            print("Failed to initialize agent")
            return
        
        print("\n🔄 Multi-Step Workflow Demo")
        print("=" * 50)
        
        # Complex workflow command
        workflow_command = """
        Go to Amazon, search for wireless headphones, filter by price under $100, 
        click on the first result, add it to cart, and take a screenshot of the cart page
        """
        
        print(f"Workflow: '{workflow_command.strip()}'")
        print("-" * 40)
        
        await agent.process_voice_input(workflow_command)
        
        print("\n✅ Workflow demo completed!")
    
    except Exception as e:
        logger.error(f"Workflow demo error: {e}")
    
    finally:
        await agent.cleanup()


async def demo_data_extraction():
    """Demo data extraction capabilities"""
    agent = VoiceBrowserAgent()
    
    try:
        if not await agent.initialize():
            print("Failed to initialize agent")
            return
        
        print("\n📊 Data Extraction Demo")
        print("=" * 50)
        
        # Data extraction commands
        extraction_commands = [
            "Go to a news website",
            "Extract all the headlines from the main page",
            "Extract all the article links",
            "Extract the publication dates",
            "Take a screenshot of the page"
        ]
        
        for command in extraction_commands:
            print(f"\n🔍 Command: '{command}'")
            await agent.process_voice_input(command)
            await asyncio.sleep(1)
        
        print("\n✅ Data extraction demo completed!")
    
    except Exception as e:
        logger.error(f"Data extraction demo error: {e}")
    
    finally:
        await agent.cleanup()


async def interactive_demo():
    """Interactive demo where user can type commands"""
    agent = VoiceBrowserAgent()
    
    try:
        if not await agent.initialize():
            print("Failed to initialize agent")
            return
        
        print("\n🎮 Interactive Demo")
        print("=" * 50)
        print("Type your commands (or 'quit' to exit):")
        print("Example: 'Go to Google and search for AI news'")
        print()
        
        while True:
            try:
                command = input("🎤 Your command: ").strip()
                
                if command.lower() in ['quit', 'exit', 'q']:
                    break
                
                if command:
                    await agent.process_voice_input(command)
                    print()
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
        
        print("\n👋 Interactive demo ended!")
    
    except Exception as e:
        logger.error(f"Interactive demo error: {e}")
    
    finally:
        await agent.cleanup()


async def main():
    """Main demo function"""
    print("🚀 Voice-Enabled Browser Agent Demo")
    print("=" * 60)
    print("Choose a demo mode:")
    print("1. Basic voice commands demo")
    print("2. Multi-step workflow demo")
    print("3. Data extraction demo")
    print("4. Interactive demo")
    print("5. Run all demos")
    print()
    
    try:
        choice = input("Enter your choice (1-5): ").strip()
        
        if choice == "1":
            await demo_voice_commands()
        elif choice == "2":
            await demo_workflow()
        elif choice == "3":
            await demo_data_extraction()
        elif choice == "4":
            await interactive_demo()
        elif choice == "5":
            await demo_voice_commands()
            await demo_workflow()
            await demo_data_extraction()
            await interactive_demo()
        else:
            print("Invalid choice. Running basic demo...")
            await demo_voice_commands()
    
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
