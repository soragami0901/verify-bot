import discord
from discord.ext import commands, tasks
import config
import server
from aiohttp import web
import asyncio
import time
import aiohttp
from pyngrok import ngrok
import sys
import os # Added for env vars
import storage  # New storage module

class AuthBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await storage.init_storage()  # Init JSON storage
        await self.load_extension("cogs.auth")
        
        # Sync Slash Commands
        try:
            # Sync globally to allow multi-service support
            # Note: Global sync can take up to an hour to propagate in some cases, but instant for dev
            await self.tree.sync()
            print("Slash commands synced globally.")
        except Exception as e:
            print(f"Failed to sync slash commands: {e}")
        
        # Start Web Server
        app = server.setup_server(self)
        runner = web.AppRunner(app)
        await runner.setup()
        # Determine Port (Render provides PORT environment variable)
        port = int(os.getenv("PORT", 8080))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"Web server started on port {port}")

        # Start ngrok
        try:
            # Open a HTTP tunnel on the specified port
            if config.NGROK_DOMAIN:
                public_url = ngrok.connect(port, domain=config.NGROK_DOMAIN).public_url
                print(f"Using Static Domain: {public_url}")
            else:
                public_url = ngrok.connect(port).public_url
                print(f"Using Random Domain: {public_url}")

            print("\n" + "="*50)
            print(f"ngrok Tunnel Started: {public_url}")
            
            # Update config with the new URL
            config.REDIRECT_URI = public_url + "/callback"
            print(f"Updated Redirect URI: {config.REDIRECT_URI}")
            
            print("IMPORTANT: You must copy the above 'Updated Redirect URI' to your Discord Developer Portal > OAuth2 > Redirects!")
            print("="*50 + "\n")
            
        except Exception as e:
            print(f"Failed to start ngrok: {e}")
            print("Please ensure ngrok is installed and authenticated if you want external access.")

        self.token_refresh_task.start()

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

    @tasks.loop(minutes=60)
    async def token_refresh_task(self):
        print("Checking for expiring tokens...")
        users_map = await storage.get_all_users()
        current_time = time.time()
        
        for user_id, user_data in users_map.items():
            expires_at = user_data.get("expires_at", 0)
            refresh = user_data.get("refresh_token")
            
            # Refresh if expiring in less than 6 hours
            if expires_at - current_time < 21600: 
                print(f"Refreshing token for user {user_id}")
                await self.refresh_user_token(int(user_id), refresh)

    async def refresh_user_token(self, user_id, refresh_token):
        data = {
            'client_id': config.CLIENT_ID,
            'client_secret': config.CLIENT_SECRET,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post('https://discord.com/api/oauth2/token', data=data) as resp:
                if resp.status == 200:
                    token_data = await resp.json()
                    
                    # Update User Data
                    user_str = str(user_id)
                    current_data = await storage.get_user(user_id) or {}
                    current_data.update({
                        "access_token": token_data['access_token'],
                        "refresh_token": token_data['refresh_token'],
                        "expires_at": time.time() + token_data['expires_in']
                    })
                    await storage.save_user(user_id, current_data)
                    
                    print(f"Token refreshed for {user_id}")
                    return token_data['access_token']
                else:
                    print(f"Failed to refresh token for {user_id}: {await resp.text()}")
                    return None

bot = AuthBot()

if __name__ == "__main__":
    if not config.BOT_TOKEN:
        print("Error: BOT_TOKEN is not set in .env")
    else:
        bot.run(config.BOT_TOKEN)
