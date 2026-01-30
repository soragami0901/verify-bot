import discord
from discord.ext import commands
from discord import ui
import storage
import config
import time
import aiohttp

# Quiz Answer
QUIZ_ANSWER = "4"

class QuizModal(ui.Modal, title='認証クイズ'):
    def __init__(self, role_id):
        super().__init__()
        self.role_id = role_id
        
    answer = ui.TextInput(label='2 + 2 = ?', placeholder='答えを入力してください')

    async def on_submit(self, interaction: discord.Interaction):
        if self.answer.value.strip() == QUIZ_ANSWER:
            role = interaction.guild.get_role(self.role_id)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    await interaction.response.send_message(f"正解です！ロール {role.name} を付与しました。", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("エラー：権限不足でロールを付与できませんでした。", ephemeral=True)
            else:
                await interaction.response.send_message("エラー：ロールが見つかりません。", ephemeral=True)
        else:
            await interaction.response.send_message("不正解です。もう一度試してください。", ephemeral=True)

class AuthCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # GLOBAL INTERACTION LISTENER for buttons
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
            
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("auth:"):
            return

        # Format: auth:method_id:role_id
        try:
            _, method_id, role_id_str = custom_id.split(":")
            role_id = int(role_id_str)
        except ValueError:
            return # Invalid format

        if method_id == "1": # Simple Click
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    await interaction.response.send_message(f"認証完了！{role.name} ロールを付与しました。", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("エラー：権限不足でロールを付与できませんでした。Botのロール順序を確認してください。", ephemeral=True)
            else:
                await interaction.response.send_message("エラー：設定されたロールが見つかりません。", ephemeral=True)

        elif method_id == "2": # Quiz
            await interaction.response.send_modal(QuizModal(role_id))
            
    # --- Helper Check for Admin ---
    async def is_bot_admin(self, interaction: discord.Interaction) -> bool:
        if await storage.is_admin(interaction.user.id, config.ROOT_ADMIN_ID):
            return True
        await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        return False

    # --- Groups ---
    auth_group = discord.app_commands.Group(name="auth", description="認証パネルの作成コマンド")
    
    # --- Auth Commands ---

    @auth_group.command(name="simple", description="簡易認証（ボタンのみ）のパネルを作成します")
    @discord.app_commands.describe(role="付与するロール")
    async def auth_simple(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(title="簡易認証", description="以下のボタンを押して認証してください。", color=discord.Color.blue())
        view = ui.View(timeout=None)
        # All buttons Green with label "認証"
        view.add_item(ui.Button(label="認証", style=discord.ButtonStyle.success, custom_id=f"auth:1:{role.id}"))
        await interaction.response.send_message(embed=embed, view=view)

    @auth_group.command(name="quiz", description="クイズ認証のパネルを作成します")
    @discord.app_commands.describe(role="付与するロール")
    async def auth_quiz(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(title="クイズ認証", description="以下のボタンを押してクイズに答えてください。", color=discord.Color.green())
        view = ui.View(timeout=None)
        view.add_item(ui.Button(label="認証", style=discord.ButtonStyle.success, custom_id=f"auth:2:{role.id}"))
        await interaction.response.send_message(embed=embed, view=view)

    @auth_group.command(name="oauth", description="アプリ連携認証のパネルを作成します")
    @discord.app_commands.describe(role="付与するロール")
    async def auth_oauth(self, interaction: discord.Interaction, role: discord.Role):
        state = f"{role.id}"
        url = f"https://discord.com/oauth2/authorize?client_id={config.CLIENT_ID}&response_type=code&redirect_uri={config.REDIRECT_URI}&scope=identify+guilds.join&state={state}"
        
        embed = discord.Embed(title="アプリ連携認証", description="以下のボタンを押して連携を許可してください。", color=discord.Color.purple())
        view = ui.View(timeout=None)
        # Link button (cannot change color, always grey-ish link style, but label can be "認証")
        view.add_item(ui.Button(label="認証", url=url, style=discord.ButtonStyle.link))
        await interaction.response.send_message(embed=embed, view=view)

    # --- User Management Commands (Root Level) ---

    @discord.app_commands.command(name="info", description="保存されたユーザーの情報を表示します")
    @discord.app_commands.describe(user="情報を表示するユーザー")
    async def info(self, interaction: discord.Interaction, user: discord.User):
        if not await self.is_bot_admin(interaction): return

        user_data = await storage.get_user(user.id)
        if not user_data:
             await interaction.response.send_message(f"{user.mention} のデータは見つかりませんでした。", ephemeral=True)
             return
             
        embed = discord.Embed(title=f"ユーザー詳細: {user_data.get('username')}", color=discord.Color.orange())
        # Use avatar from JSON or fallback to current avatar
        avatar_url = user_data.get('avatar_url') or (user.display_avatar.url if user.display_avatar else None)
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
            
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
        
        ip_addr = user_data.get('ip_address', 'Unknown')
        ip_label = "IP Address"
        if ":" in ip_addr:
            ip_label += " (IPv6)"
        elif "." in ip_addr:
            ip_label += " (IPv4)"
        
        embed.add_field(name=ip_label, value=f"`{ip_addr}`", inline=True)
        
        # Mask Token for security in display
        token = user_data.get('access_token', '')
        masked_token = f"||{token[:15]}...||" if token else "None"
        embed.add_field(name="Access Token", value=masked_token, inline=False)
        embed.add_field(name="Expires At", value=f"<t:{int(user_data.get('expires_at', 0))}:R> (<t:{int(user_data.get('expires_at', 0))}:f>)", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="list", description="保存されている全ユーザーを表示します")
    async def list_users(self, interaction: discord.Interaction):
        if not await self.is_bot_admin(interaction): return

        users_map = await storage.get_all_users()
        if not users_map:
            await interaction.response.send_message("保存されているユーザーはいません。", ephemeral=True)
            return

        embed = discord.Embed(title=f"保存済みユーザー一覧 ({len(users_map)}名)", color=discord.Color.gold())
        description = ""
        for uid, data in users_map.items():
            line = f"• <@{uid}> (`{uid}`) - {data.get('username')}\n"
            if len(description) + len(line) > 4000:
                description += "...(他多数)"
                break
            description += line
        
        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="removeuser", description="指定ユーザーの認証データを削除します")
    async def remove_user_data(self, interaction: discord.Interaction, user: discord.User):
        if not await self.is_bot_admin(interaction): return
        
        if await storage.remove_user(user.id):
            await interaction.response.send_message(f"{user.mention} の認証データを削除しました。これ以降 `/join` の対象になりません。", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} のデータは見つかりませんでした。", ephemeral=True)

    # --- Admin Management Commands ---

    @discord.app_commands.command(name="add", description="Botの管理者(/join権限)を追加します")
    async def add_admin(self, interaction: discord.Interaction, user: discord.User):
        if not await self.is_bot_admin(interaction): return

        await storage.add_admin(user.id)
        await interaction.response.send_message(f"{user.mention} をBot管理者に追加しました。`/join` が使用可能です。", ephemeral=True)

    @discord.app_commands.command(name="remove", description="Botの管理者権限を剥奪します")
    async def remove_admin(self, interaction: discord.Interaction, user: discord.User):
        if not await self.is_bot_admin(interaction): return

        if user.id == config.ROOT_ADMIN_ID:
            await interaction.response.send_message("ルート管理者は削除できません。", ephemeral=True)
            return

        await storage.remove_admin(user.id)
        await interaction.response.send_message(f"{user.mention} の管理者権限を削除しました。", ephemeral=True)

    # --- Admin Helper Commands ---

    @discord.app_commands.command(name="sync", description="スラッシュコマンドをDiscordに同期します(管理者のみ)")
    async def sync_commands(self, interaction: discord.Interaction):
        if not await self.is_bot_admin(interaction): return
        
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.tree.sync()
            await interaction.followup.send("スラッシュコマンドの同期が完了しました！反映まで時間がかかる場合があります。")
        except Exception as e:
            await interaction.followup.send(f"同期に失敗しました: {e}")

    # --- Join Command ---
    
    @discord.app_commands.command(name="join", description="連携済みのユーザーをサーバーに参加させます(指定なしで全員)")
    @discord.app_commands.describe(target="参加させるユーザー（省略すると全員参加させます）")
    async def join_server(self, interaction: discord.Interaction, target: discord.User = None):
        # Check Admin
        if not await self.is_bot_admin(interaction): return
        
        await interaction.response.defer(ephemeral=True)
        
        if target:
            # Single join logic
            await self._perform_join(interaction, target.id, target.mention)
        else:
            # Bulk join logic
            users_map = await storage.get_all_users()
            if not users_map:
                await interaction.followup.send("保存されているユーザーはいません。")
                return
            
            await interaction.followup.send(f"{len(users_map)} 名の参加処理を開始します...")
            
            success_count = 0
            fail_count = 0
            already_in_count = 0
            
            for uid_str, user_data in users_map.items():
                uid = int(uid_str)
                # Check if user is already in guild (to avoid wasting API calls)
                if interaction.guild.get_member(uid):
                    already_in_count += 1
                    continue
                
                res = await self._perform_join_logic(interaction.guild.id, uid, user_data)
                if res == "success":
                    success_count += 1
                elif res == "already_in":
                    already_in_count += 1
                else:
                    fail_count += 1
                
                # Small sleep to be safe with rate limits during bulk
                await asyncio.sleep(0.5)
            
            await interaction.followup.send(
                f"参加処理が完了しました。\n"
                f"✅ 成功: {success_count}名\n"
                f"🏠 既にサーバー内: {already_in_count}名\n"
                f"❌ 失敗: {fail_count}名"
            )

    async def _perform_join(self, interaction: discord.Interaction, user_id: int, mention: str):
        # Specific helper for single user with feedback
        if interaction.guild.get_member(user_id):
             await interaction.followup.send(f"{mention} は既にサーバーにいます。")
             return

        user_data = await storage.get_user(user_id)
        if not user_data:
            await interaction.followup.send(f"{mention} の認証データが見つかりません。")
            return

        res = await self._perform_join_logic(interaction.guild.id, user_id, user_data)
        if res == "success":
            await interaction.followup.send(f"{mention} をサーバーに参加させました！")
        elif res == "already_in":
            await interaction.followup.send(f"{mention} は既にサーバーに参加済みです。")
        else:
            await interaction.followup.send(f"{mention} の参加処理に失敗しました。詳細: {res}")

    async def _perform_join_logic(self, guild_id: int, user_id: int, user_data: dict) -> str:
        # Core join logic returning status string
        access_token = user_data["access_token"]
        refresh_token = user_data["refresh_token"]
        expires_at = user_data.get("expires_at", 0)
        
        if time.time() > expires_at - 60:
            new_access = await self.bot.refresh_user_token(user_id, refresh_token)
            if new_access:
                access_token = new_access
            else:
                return "token_refresh_failed"

        url = f"https://discord.com/api/guilds/{guild_id}/members/{user_id}"
        headers = {
            "Authorization": f"Bot {config.BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        json_body = {"access_token": access_token}
        
        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, json=json_body) as resp:
                if resp.status in (201, 204):
                    return "success"
                elif resp.status == 200:
                    return "already_in"
                else:
                    return f"api_error_{resp.status}"

async def setup(bot):
    await bot.add_cog(AuthCog(bot))
