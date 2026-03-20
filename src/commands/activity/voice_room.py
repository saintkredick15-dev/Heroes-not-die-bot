import discord
from discord import app_commands
from discord.ext import commands
from modules.db import get_database
import asyncio

db = get_database()

class RoomNameModal(discord.ui.Modal, title="Змінити назву кімнати"):
    name_input = discord.ui.TextInput(
        label="Нова назва кімнати",
        placeholder="Введіть нову назву...",
        max_length=100,
        required=True
    )

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value
        
        user_room = await db.private_rooms.find_one({
            "owner_id": self.user_id,
            "active": True
        })
        
        if user_room:
            channel = interaction.guild.get_channel(user_room["channel_id"])
            if channel:
                await channel.edit(name=new_name)
                
                await db.private_rooms.update_one(
                    {"owner_id": self.user_id, "active": True},
                    {"$set": {"name": new_name}}
                )
                await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Назву кімнати змінено на: **{new_name}**", ephemeral=True)
            else:
                await interaction.response.send_message("<:cutiex:1480246146076119132> Не вдалося знайти твою кімнату!", ephemeral=True)
        else:
            await interaction.response.send_message("<:cutiex:1480246146076119132> У тебе немає активної приватної кімнати!", ephemeral=True)

class RoomLimitModal(discord.ui.Modal, title="Встановити ліміт користувачів"):
    limit_input = discord.ui.TextInput(
        label="Ліміт користувачів",
        placeholder="Введіть число від 0 до 99 (0 = без ліміту)",
        max_length=2,
        required=True
    )

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.limit_input.value)
            if limit < 0 or limit > 99:
                await interaction.response.send_message("<:cutiex:1480246146076119132> Ліміт має бути від 0 до 99!", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Введіть правильне число!", ephemeral=True)
            return

        user_room = await db.private_rooms.find_one({
            "owner_id": self.user_id,
            "active": True
        })
        
        if user_room:
            channel = interaction.guild.get_channel(user_room["channel_id"])
            if channel:
                await channel.edit(user_limit=limit if limit > 0 else None)
                await db.private_rooms.update_one(
                    {"owner_id": self.user_id, "active": True},
                    {"$set": {"user_limit": limit}}
                )
                limit_text = f"{limit} користувачів" if limit > 0 else "без ліміту"
                await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Ліміт кімнати встановлено: **{limit_text}**", ephemeral=True)
            else:
                await interaction.response.send_message("<:cutiex:1480246146076119132> Не вдалося знайти твою кімнату!", ephemeral=True)
        else:
            await interaction.response.send_message("<:cutiex:1480246146076119132> У тебе немає активної приватної кімнати!", ephemeral=True)

class UserMentionModal(discord.ui.Modal):
    user_input = discord.ui.TextInput(
        label="Згадай користувача",
        placeholder="@користувач або ID користувача",
        required=True
    )

    def __init__(self, user_id, action_type, title):
        super().__init__(title=title)
        self.user_id = user_id
        self.action_type = action_type

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.user_input.value.strip()
        target_user = None
        
        if user_input.startswith('<@') and user_input.endswith('>'):
            
            user_id = user_input[2:-1].replace('!', '')
            try:
                target_user = await interaction.guild.fetch_member(int(user_id))
            except (ValueError, discord.HTTPException):
                pass
        else:
            
            try:
                target_user = await interaction.guild.fetch_member(int(user_input))
            except (ValueError, discord.HTTPException):
                
                target_user = discord.utils.get(interaction.guild.members, display_name=user_input)
                if not target_user:
                    target_user = discord.utils.get(interaction.guild.members, name=user_input)

        if not target_user:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Користувача не знайдено!", ephemeral=True)
            return

        user_room = await db.private_rooms.find_one({
            "owner_id": self.user_id,
            "active": True
        })
        
        if not user_room:
            await interaction.response.send_message("<:cutiex:1480246146076119132> У тебе немає активної приватної кімнати!", ephemeral=True)
            return

        channel = interaction.guild.get_channel(user_room["channel_id"])
        if not channel:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Не вдалося знайти твою кімнату!", ephemeral=True)
            return

        if self.action_type == "access":
            
            overwrites = channel.overwrites
            if target_user in overwrites:
                
                del overwrites[target_user]
                await channel.edit(overwrites=overwrites)
                await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Скинуто права доступу для {target_user.display_name}", ephemeral=True)
            else:
                
                overwrites[target_user] = discord.PermissionOverwrite(connect=True, view_channel=True)
                await channel.edit(overwrites=overwrites)
                await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Надано доступ користувачеві {target_user.display_name}", ephemeral=True)
                
        elif self.action_type == "mic":
            
            overwrites = channel.overwrites
            current_perms = overwrites.get(target_user, discord.PermissionOverwrite())
            if current_perms.speak is False:
                
                current_perms.speak = True
                overwrites[target_user] = current_perms
                await channel.edit(overwrites=overwrites)
                await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Повернуто право говорити для {target_user.display_name}", ephemeral=True)
            else:
                
                current_perms.speak = False
                overwrites[target_user] = current_perms
                await channel.edit(overwrites=overwrites)
                await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Заборонено говорити користувачеві {target_user.display_name}", ephemeral=True)
                
        elif self.action_type == "kick":
            
            if target_user.voice and target_user.voice.channel == channel:
                await target_user.move_to(None)
                await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Користувача {target_user.display_name} вигнано з кімнати", ephemeral=True)
            else:
                await interaction.response.send_message(f"<:cutiex:1480246146076119132> Користувач {target_user.display_name} не в твоїй кімнаті", ephemeral=True)
                
        elif self.action_type == "reset":
            
            overwrites = channel.overwrites
            if target_user in overwrites:
                del overwrites[target_user]
                await channel.edit(overwrites=overwrites)
                await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Скинуто всі права для {target_user.display_name}", ephemeral=True)
            else:
                await interaction.response.send_message(f"<:cutiex:1480246146076119132> У користувача {target_user.display_name} немає особливих прав", ephemeral=True)
                
        elif self.action_type == "owner":
            
            await db.private_rooms.update_one(
                {"owner_id": self.user_id, "active": True},
                {"$set": {"owner_id": target_user.id}}
            )
            
            overwrites = channel.overwrites
            
            overwrites[interaction.user] = discord.PermissionOverwrite(
                connect=True, view_channel=True, manage_channels=False, manage_permissions=False
            )
            
            overwrites[target_user] = discord.PermissionOverwrite(
                connect=True, view_channel=True, manage_channels=True, manage_permissions=True
            )
            await channel.edit(overwrites=overwrites)
            
            await interaction.response.send_message(f"<:cutiecheckmark:1479120440734650389> Власність кімнати передано користувачеві {target_user.display_name}", ephemeral=True)

class RoomManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Перевіряє чи користувач має право використовувати кнопки"""
        user_room = await db.private_rooms.find_one({
            "owner_id": interaction.user.id,
            "active": True
        })
        
        if not user_room:
            await interaction.response.send_message("<:cutiex:1480246146076119132> У тебе немає приватного каналу! Зайди в канал-створювач щоб створити свій.", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="<:pen:1405110194651795466>", style=discord.ButtonStyle.secondary, row=0, custom_id="room_edit_name")
    async def edit_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Змінити назву кімнати"""
        modal = RoomNameModal(interaction.user.id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="<:members_limit:1405110200708497419>", style=discord.ButtonStyle.secondary, row=0, custom_id="room_set_limit")
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Встановити ліміт користувачів"""
        modal = RoomLimitModal(interaction.user.id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="<:lock_unlock:1405110188259934298>", style=discord.ButtonStyle.secondary, row=0, custom_id="room_toggle_lock")
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Закрити/відкрити доступ"""
        user_room = await db.private_rooms.find_one({
            "owner_id": interaction.user.id,
            "active": True
        })
        
        if user_room:
            channel = interaction.guild.get_channel(user_room["channel_id"])
            if channel:
                overwrites = channel.overwrites
                everyone = interaction.guild.default_role
                
                current_perms = overwrites.get(everyone, discord.PermissionOverwrite())
                if current_perms.connect is False:
                    
                    current_perms.connect = None  
                    overwrites[everyone] = current_perms
                    await channel.edit(overwrites=overwrites)
                    await db.private_rooms.update_one(
                        {"owner_id": interaction.user.id, "active": True},
                        {"$set": {"locked": False}}
                    )
                    await interaction.response.send_message("🔓 Кімнату відкрито для всіх!", ephemeral=True)
                else:
                    
                    current_perms.connect = False
                    overwrites[everyone] = current_perms
                    await channel.edit(overwrites=overwrites)
                    await db.private_rooms.update_one(
                        {"owner_id": interaction.user.id, "active": True},
                        {"$set": {"locked": True}}
                    )
                    await interaction.response.send_message("🔒 Кімнату закрито для нових користувачів!", ephemeral=True)

    @discord.ui.button(emoji="<:eye_closed:1405110183385894932>", style=discord.ButtonStyle.secondary, row=0, custom_id="room_toggle_visibility")
    async def toggle_visibility(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Сховати/показати кімнату"""
        user_room = await db.private_rooms.find_one({
            "owner_id": interaction.user.id,
            "active": True
        })
        
        if user_room:
            channel = interaction.guild.get_channel(user_room["channel_id"])
            if channel:
                overwrites = channel.overwrites
                everyone = interaction.guild.default_role
                
                current_perms = overwrites.get(everyone, discord.PermissionOverwrite())
                if current_perms.view_channel is False:
                    
                    current_perms.view_channel = None
                    overwrites[everyone] = current_perms
                    await channel.edit(overwrites=overwrites)
                    await db.private_rooms.update_one(
                        {"owner_id": interaction.user.id, "active": True},
                        {"$set": {"hidden": False}}
                    )
                    await interaction.response.send_message("👁️ Кімнату зроблено видимою для всіх!", ephemeral=True)
                else:
                    
                    current_perms.view_channel = False
                    overwrites[everyone] = current_perms
                    await channel.edit(overwrites=overwrites)
                    await db.private_rooms.update_one(
                        {"owner_id": interaction.user.id, "active": True},
                        {"$set": {"hidden": True}}
                    )
                    await interaction.response.send_message("🙈 Кімнату сховано від інших користувачів!", ephemeral=True)

    @discord.ui.button(emoji="<:plus:1405110182014357595>", style=discord.ButtonStyle.secondary, row=0, custom_id="room_manage_access")
    async def manage_access(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Управління доступом користувачів"""
        modal = UserMentionModal(interaction.user.id, "access", "Управління доступом")
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="<:microphone:1405110190239514654>", style=discord.ButtonStyle.secondary, row=1, custom_id="room_manage_mic")
    async def manage_mic(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Управління правами мікрофону"""
        modal = UserMentionModal(interaction.user.id, "mic", "Управління мікрофоном")
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="<:kick_user:1405110186313519226>", style=discord.ButtonStyle.secondary, row=1, custom_id="room_kick_user")
    async def kick_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Вигнати користувача"""
        modal = UserMentionModal(interaction.user.id, "kick", "Вигнати користувача")
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="<:reset:1405110197248069733>", style=discord.ButtonStyle.secondary, row=1, custom_id="room_reset_permissions")
    async def reset_permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Скинути права користувача"""
        modal = UserMentionModal(interaction.user.id, "reset", "Скинути права")
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="<:star_owner:1405110192462495744>", style=discord.ButtonStyle.secondary, row=1, custom_id="room_transfer_ownership")
    async def transfer_ownership(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Передати власність"""
        modal = UserMentionModal(interaction.user.id, "owner", "Передати власність")
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="<:room_info:1405110199127248896>", style=discord.ButtonStyle.primary, row=1, custom_id="room_info")
    async def room_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Інформація про кімнату"""
        user_room = await db.private_rooms.find_one({
            "owner_id": interaction.user.id,
            "active": True
        })
        
        if user_room:
            channel = interaction.guild.get_channel(user_room["channel_id"])
            if channel:
                
                member_count = len(channel.members) if hasattr(channel, 'members') else 0
                limit = user_room.get("user_limit", 0)
                limit_text = f"{limit} користувачів" if limit > 0 else "без ліміту"
                locked = user_room.get("locked", False)
                hidden = user_room.get("hidden", False)
                
                embed = discord.Embed(
                    title="📋 Інформація про твою кімнату",
                    color=0x7c7cf0,
                    description=(
                        f"🏠 **Назва:** {channel.name}\n"
                        f"👥 **Учасників:** {member_count}\n"
                        f"📊 **Ліміт:** {limit_text}\n"
                        f"🔒 **Статус:** {'Закрито' if locked else 'Відкрито'}\n"
                        f"👁️ **Видимість:** {'Сховано' if hidden else 'Видимо всім'}\n"
                        f"👑 **Власник:** <@{interaction.user.id}>"
                    )
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("<:cutiex:1480246146076119132> Не вдалося знайти твою кімнату!", ephemeral=True)
        else:
            await interaction.response.send_message("<:cutiex:1480246146076119132> У тебе немає активної приватної кімнати!", ephemeral=True)

class RoomManagementCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        
        await db.server_configs.create_index("guild_id", unique=True, background=True)
        await db.private_rooms.create_index("owner_id", background=True)
        await db.private_rooms.create_index("channel_id", background=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Обробляє зміни voice статусу"""
        
        if after.channel:
            
            server_config = await db.server_configs.find_one({"guild_id": member.guild.id})
            if server_config and after.channel.id == server_config.get("creator_channel_id"):
                await self.create_private_room(member, after.channel)
        
        if before.channel:
            user_room = await db.private_rooms.find_one({
                "channel_id": before.channel.id,
                "active": True
            })
            if user_room and len(before.channel.members) == 0:
                
                await self.delete_private_room(before.channel, user_room)

    async def create_private_room(self, member, creator_channel):
        """Створити приватну кімнату для користувача"""
        
        existing_room = await db.private_rooms.find_one({
            "owner_id": member.id,
            "active": True
        })
        
        if existing_room:
            
            existing_channel = member.guild.get_channel(existing_room["channel_id"])
            if existing_channel:
                await member.move_to(existing_channel)
                return

        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
            member: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, manage_permissions=True)
        }

        channel_name = f"{member.display_name}'s Room"
        private_channel = await creator_channel.category.create_voice_channel(
            name=channel_name,
            overwrites=overwrites,
            user_limit=None
        )

        await member.move_to(private_channel)

        await db.private_rooms.insert_one({
            "owner_id": member.id,
            "channel_id": private_channel.id,
            "guild_id": member.guild.id,
            "name": channel_name,
            "active": True,
            "user_limit": 0,
            "locked": False,
            "hidden": False,
            "created_at": discord.utils.utcnow()
        })

    async def delete_private_room(self, channel, room_data):
        """Видалити приватну кімнату"""
        await channel.delete()
        await db.private_rooms.update_one(
            {"_id": room_data["_id"]},
            {"$set": {"active": False, "deleted_at": discord.utils.utcnow()}}
        )

    @app_commands.command(name="room-setup", description="Налаштування системи приватних кімнат — вкажіть канал-створювач і канал управління")
    @app_commands.describe(
        creator_channel="Voice канал де користувачі створюють свої кімнати",
        management_channel="Text канал куди відправити панель управління кімнатами"
    )
    @app_commands.default_permissions(administrator=True)
    async def room_setup(self, interaction: discord.Interaction, 
                        creator_channel: discord.VoiceChannel, 
                        management_channel: discord.TextChannel):
        """Налаштування системи приватних кімнат для адмінів"""
        
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("<:cutiex:1480246146076119132> У тебе немає прав для використання цієї команди!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async for message in management_channel.history(limit=50):
            if message.author == interaction.client.user and message.embeds:
                if message.embeds[0].title == "🏠 Управління приватною кімнатою":
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass
                    break

        await db.server_configs.update_one(
            {"guild_id": interaction.guild.id},
            {
                "$set": {
                    "creator_channel_id": creator_channel.id,
                    "management_channel_id": management_channel.id,
                    "configured_by": interaction.user.id,
                    "configured_at": discord.utils.utcnow()
                }
            },
            upsert=True
        )

        embed = discord.Embed(
            title="🏠 Управління приватною кімнатою",
            color=0x7c7cf0,
            description=(
                "Натисни наступні кнопочки, щоб налаштувати свою кімнату\n"
                "Використовувати їх можна тільки коли у тебе є приватний канал\n\n"
                "<:pen:1405110194651795466> — змінити назву кімнати\n"
                "<:members_limit:1405110200708497419> — встановити ліміт користувачів\n"
                "<:lock_unlock:1405110188259934298> — закрити/відкрити доступ в кімнату\n"
                "<:eye_closed:1405110183385894932> — сховати/розкрити кімнату для всіх\n"
                "<:plus:1405110182014357595> — заборонити/дати доступ до кімнати користувачеві\n"
                "<:microphone:1405110190239514654> — заборонити/дати право говорити користувачеві\n"
                "<:kick_user:1405110186313519226> — вигнати користувача з кімнати\n"
                "<:reset:1405110197248069733> — скинути права користувача\n"
                "<:star_owner:1405110192462495744> — зробити користувача новим власником\n"
                "<:room_info:1405110199127248896> — інформація про кімнату"
            )
        )

        view = RoomManagementView()
        
        await management_channel.send(embed=embed, view=view)

        success_embed = discord.Embed(
            title="<:cutiecheckmark:1479120440734650389> Система приватних кімнат налаштована!",
            color=0x00ff00,
            description=(
                f"**Канал-створювач:** {creator_channel.mention}\n"
                f"**Канал управління:** {management_channel.mention}\n\n"
                f"Тепер користувачі можуть:\n"
                f"• Заходити в {creator_channel.mention} щоб створити приватну кімнату\n"
                f"• Використовувати панель управління в {management_channel.mention} для налаштування своїх кімнат"
            )
        )

        await interaction.followup.send(embed=success_embed, ephemeral=True)

    async def get_user_private_channel(self, user_id):
        """Отримати приватний канал користувача з БД"""
        user_room = await db.private_rooms.find_one({
            "owner_id": user_id,
            "active": True
        })
        return user_room

async def setup(bot):
    
    view = RoomManagementView()
    bot.add_view(view)
    print("<:cutiecheckmark:1479120440734650389> Room Management persistent view зареєстровано")
    
    await bot.add_cog(RoomManagementCommands(bot))
