from aiohttp import web
import aiohttp
import config
import storage
import discord
import time

routes = web.RouteTableDef()

def setup_server(bot):
    app = web.Application()
    app.add_routes(routes)
    app["bot"] = bot
    return app

@routes.get('/')
async def index(request):
    return web.Response(text="Bot is running!", content_type='text/plain')

@routes.get('/callback')
async def callback(request):
    code = request.query.get('code')
    state = request.query.get('state') 
    
    if not code or not state:
        return web.Response(text="Error: Missing code or state.")

    try:
        # State format now: "role_id" (user_id is fetched via token)
        # Or if we wanted to support multiple args we could but currently just role_id
        role_id = int(state)
    except ValueError:
        return web.Response(text="Error: Invalid state format (Role ID missing).")

    # Exchange code for token
    data = {
        'client_id': config.CLIENT_ID,
        'client_secret': config.CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': config.REDIRECT_URI
    }

    async with aiohttp.ClientSession() as session:
        async with session.post('https://discord.com/api/oauth2/token', data=data) as resp:
            if resp.status != 200:
                return web.Response(text=f"Error fetching token: {await resp.text()}")
            token_data = await resp.json()

    # Save to DB (We need user_id first!)
    access_token = token_data['access_token']
    
    # Fetch User ID & Profile
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get('https://discord.com/api/users/@me', headers=headers) as user_resp:
            if user_resp.status != 200:
                return web.Response(text="Error: Failed to fetch user profile from Discord.")
            user_data_api = await user_resp.json()
            user_id = int(user_data_api['id'])
            username = user_data_api.get('username')
            avatar = user_data_api.get('avatar')
            avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png" if avatar else None

    # Capture IP
    # If behind ngrok, the real IP is in X-Forwarded-For
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        ip_address = forwarded_for.split(',')[0].strip()
    else:
        ip_address = request.remote

    # Save to JSON Storage
    user_data_dict = {
        "user_id": user_id,
        "username": username,
        "avatar_url": avatar_url,
        "ip_address": ip_address,
        "access_token": access_token,
        "refresh_token": token_data['refresh_token'],
        "expires_at": time.time() + token_data['expires_in']
    }
    await storage.save_user(user_id, user_data_dict)

    # Grant Role
    bot = request.app["bot"]
    # We need to find the guild where this role belongs. 
    # Since we don't have guild_id in state, we have to search common guilds or pass guild_id in state too.
    # Improved State: "user_id:role_id:guild_id" would be best, but let's try to find the role in shared guilds.
    
    # Actually, we can get the guild from the role_id if we iterate, OR just pass guild_id in state.
    # Let's assume we search all guilds.
    
    target_guild = None
    target_role = None
    target_member = None
    
    for guild in bot.guilds:
        role = guild.get_role(role_id)
        if role:
            target_guild = guild
            target_role = role
            target_member = guild.get_member(user_id)
            break
    
    if target_guild and target_role and target_member:
        try:
            await target_member.add_roles(target_role)
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>認証完了</title>
                <style>
                    body { font-family: sans-serif; text-align: center; margin-top: 50px; background-color: #2c2f33; color: #ffffff; }
                    .container { padding: 20px; }
                    h1 { color: #43b581; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>認証が完了しました</h1>
                    <p>このタブを閉じてDiscordに戻ってください。</p>
                </div>
            </body>
            </html>
            """
            return web.Response(text=html_content, content_type='text/html')
        except Exception as e:
            return web.Response(text=f"Role grant error: {str(e)}")
    else:
        return web.Response(text="Error: Could not find the server, member, or role. Please ensure you share a server with the bot.")
    
    return web.Response(text="Authentication processing complete.")
