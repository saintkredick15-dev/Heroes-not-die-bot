import discord
import time
import asyncio
from modules.db import get_database
from commands.administration.economy_setup import get_eco
from repositories.user import get_user
from utils.eco_helpers import make_log

db = get_database()

E_COIN = "<:coin:1478487028105482485>"
E_AUCTION = "<:Auction:1479863712855621805>"
E_CLOCK = "<:clock:1476209087804084328>"
E_CHECK = "<:cutiecheckmark:1479120440734650389>"
E_CROSS = "<:krestik:1476693091355463842>"

class CustomBidModal(discord.ui.Modal, title="Зробити свою ставку"):
    amount = discord.ui.TextInput(label="Сума ставки", max_length=15)

    def __init__(self, auction_view):
        super().__init__()
        self.auction_view = auction_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.amount.value)
            if val <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message(f"{E_CROSS} Будь ласка, введіть коректне число.", ephemeral=True)
            
        await self.auction_view.process_bid(interaction, val)

class AuctionView(discord.ui.View):
    def __init__(self, manager, guild_id: int, lot: dict, eco: dict):
        super().__init__(timeout=None) 
        self.manager = manager
        self.guild_id = guild_id
        self.lot = lot
        self.eco = eco
        
        self.current_bid = lot["start_bid"]
        self.highest_bidder = None 
        
        self.end_time = time.time() + lot["duration"]
        self.anti_snipe = eco.get("auction_anti_snipe_seconds", 30)

    async def process_bid(self, interaction: discord.Interaction, bid_amount: int):
        user_id = interaction.user.id
        guild_id = self.guild_id
        
        if time.time() > self.end_time:
            return await interaction.response.send_message(f"{E_CROSS} Аукціон вже завершено!", ephemeral=True)
            
        if bid_amount <= self.current_bid and self.highest_bidder is not None:
            return await interaction.response.send_message(f"{E_CROSS} Ваша ставка повинна бути більшою за `{self.current_bid:,}` {self.eco['currency_emoji']}!", ephemeral=True)
        
        if bid_amount < self.current_bid and self.highest_bidder is None:
            return await interaction.response.send_message(f"{E_CROSS} Початкова ставка `{self.current_bid:,}` {self.eco['currency_emoji']}!", ephemeral=True)
            
        if self.highest_bidder == user_id:
            return await interaction.response.send_message(f"{E_CROSS} Ваша ставка вже є найвищою!", ephemeral=True)
            
        user_bal = await get_user(db, guild_id, user_id)
        bank = user_bal.get("bank", 0)
        cash = user_bal.get("wallet", 0)
        
        if bank + cash < bid_amount:
            return await interaction.response.send_message(f"{E_CROSS} У вас недостатньо коштів! (Готівка + Банк: {bank+cash:,})", ephemeral=True)
            
        if self.highest_bidder:
            await db.users.update_one(
                {"guild_id": guild_id, "user_id": self.highest_bidder},
                {"$inc": {"wallet": self.current_bid}}
            )
            from modules.db import invalidate_user_data
            await invalidate_user_data(guild_id, self.highest_bidder)
            
        to_deduct = bid_amount
        if bank >= to_deduct:
            await db.users.update_one(
                {"guild_id": guild_id, "user_id": user_id},
                {"$inc": {"bank": -to_deduct}},
            )
        else:
            to_deduct -= bank
            await db.users.update_one(
                {"guild_id": guild_id, "user_id": user_id},
                {"$set": {"bank": 0}, "$inc": {"wallet": -to_deduct}},
            )
        from modules.db import invalidate_user_data
        await invalidate_user_data(guild_id, user_id)
            
        self.current_bid = bid_amount
        self.highest_bidder = user_id
        
        time_left = self.end_time - time.time()
        if time_left < self.anti_snipe and self.anti_snipe > 0:
            self.end_time += self.anti_snipe
            
        await interaction.response.send_message(f"{E_CHECK} Ви успішно поставили **{bid_amount:,}** {self.eco['currency_emoji']}!", ephemeral=True)

    @discord.ui.button(label="+100", style=discord.ButtonStyle.primary, custom_id="auc_plus_100")
    async def btn_plus_100(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_bid(interaction, self.current_bid + 100)

    @discord.ui.button(label="+1,000", style=discord.ButtonStyle.primary, custom_id="auc_plus_1000")
    async def btn_plus_1000(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_bid(interaction, self.current_bid + 1000)
        
    @discord.ui.button(label="+5,000", style=discord.ButtonStyle.primary, custom_id="auc_plus_5000")
    async def btn_plus_5000(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_bid(interaction, self.current_bid + 5000)

    @discord.ui.button(label="Власна ставка", style=discord.ButtonStyle.success, emoji="✍️", custom_id="auc_custom")
    async def btn_custom(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomBidModal(self))

class AuctionManager:
    
    def __init__(self, bot):
        self.bot = bot
        self.active_auctions = {} 

    async def start_auction(self, guild_id: int, lot: dict, channel: discord.TextChannel, eco: dict):
        
        if guild_id in self.active_auctions:
            return False, "На цьому сервері вже йде аукціон."
            
        view = AuctionView(self, guild_id, lot, eco)
        
        embed = self._build_embed(lot, view, eco)
        msg = await channel.send(embed=embed, view=view)
        
        task = self.bot.loop.create_task(self._auction_loop(guild_id, msg, view, eco))
        
        self.active_auctions[guild_id] = {
            "task": task,
            "message": msg,
            "view": view
        }
        
        return True, "Аукціон запущено."

    def _build_embed(self, lot: dict, view: AuctionView, eco: dict) -> discord.Embed:
        curr = eco.get("currency_emoji", E_COIN)
        embed = discord.Embed(
            title=f"{E_AUCTION} Аукціон: {lot['name']}",
            description=f"**Опис:**\n{lot.get('desc', 'Немає')}",
            color=0x1a1a2e
        )
        embed.add_field(name="Лідируюча ставка", value=f"`{view.current_bid:,}` {curr}", inline=True)
        
        bidder_str = f"<@{view.highest_bidder}>" if view.highest_bidder else "*Немає ставок*"
        embed.add_field(name="Лідер", value=bidder_str, inline=True)
        
        time_left = max(0, int(view.end_time - time.time()))
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="⏱ Залишилось", value=f"<t:{int(view.end_time)}:R> (<t:{int(view.end_time)}:T>)", inline=True)
        
        return embed

    async def _auction_loop(self, guild_id: int, message: discord.Message, view: AuctionView, eco: dict):
        last_update = time.time()
        try:
            while time.time() < view.end_time:
                
                if time.time() - last_update >= 5:
                    try:
                        embed = self._build_embed(view.lot, view, eco)
                        await message.edit(embed=embed, view=view)
                        last_update = time.time()
                    except discord.NotFound:
                        
                        break
                    except Exception as e:
                        print(f"Auction update error: {e}")
                
                await asyncio.sleep(1)
                
            await self._finish_auction(guild_id, message, view, eco)
            
        except asyncio.CancelledError:
            pass
        finally:
            self.active_auctions.pop(guild_id, None)

    async def _finish_auction(self, guild_id: int, message: discord.Message, view: AuctionView, eco: dict):
        
        try:
            for child in view.children:
                child.disabled = True
            
            embed = self._build_embed(view.lot, view, eco)
            embed.color = discord.Color.green() if view.highest_bidder else discord.Color.red()
            embed.clear_fields()
            
            if view.highest_bidder:
                amount = view.current_bid
                embed.title = f"{E_CHECK} Аукціон завершено: {view.lot['name']}"
                embed.description = f"<:firecracker:1479953348185555077> Переможець: <@{view.highest_bidder}>\n<:Coins:1478486725113286899> Фінальна ставка: `{amount:,}` {eco['currency_emoji']}\n\n*Перевірте свій інвентар або ролі!*"
                
                import re
                role_match = re.search(r"<@&(\d+)>", view.lot["name"])
                if role_match:
                    role_id = int(role_match.group(1))
                    guild = message.guild
                    if guild:
                        member = guild.get_member(view.highest_bidder)
                        role = guild.get_role(role_id)
                        if member and role:
                            try:
                                await member.add_roles(role, reason="Виграш в аукціоні")
                                embed.description += "\n\n🔰 **Видано роль!**"
                            except Exception:
                                embed.description += "\n\n<:warn:1477376152191373504> Помилка видачі ролі (перевірте права бота)."
                else:
                    await db.inventory.update_one(
                        {"guild_id": guild_id, "user_id": view.highest_bidder},
                        {"$push": {"items": {"type": "auction_lot", "name": view.lot["name"], "purchased_for": amount}}},
                        upsert=True
                    )
            else:
                embed.title = f"{E_CROSS} Аукціон завершено: {view.lot['name']}"
                embed.description = "Ставок не було. Лот ніхто не купив."
                
            await message.edit(embed=embed, view=view)
            
        except Exception as e:
            print(f"Помилка фіналу аукціону: {e}")

auction_manager = None

def setup_auction_manager(bot):
    global auction_manager
    if auction_manager is None:
        auction_manager = AuctionManager(bot)
    return auction_manager
