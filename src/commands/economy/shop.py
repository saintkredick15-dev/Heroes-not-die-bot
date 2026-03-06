"""
/shop — Магазин з кнопками купівлі.
/buy інтегровано: кнопки прямо в /shop embed.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import time
import random

from modules.db import get_database
from repositories.user import get_user
from commands.administration.economy_setup import get_eco

db = get_database()

E_COIN   = "<:coin:1478487028105482485>"
E_CROSS  = "<:krestik:1476693091355463842>"
E_CHECK  = "<:cutiecheckmark:1479120440734650389>"
E_SHIELD = "<:shield:1478800925664612372>"
E_STAR   = "<:reactionstar:1475954213455532067>"
E_BANK   = "<:bank:1478483868867891261>"

COLOR    = 0x1a1a2e

# ── Предмети ──────────────────────────────────────────────────────────────────

SYSTEM_ITEMS = [
    {
        "id":       "shield",
        "name":     "Щит",
        "desc":     "Захист від пограбування на 24 години",
        "emoji":    E_SHIELD,
        "duration": 86400,
        "price_key":"shop_shield_price",
        "default":  5000,
    },
    {
        "id":       "coin_boost",
        "name":     "Coin Буст",
        "desc":     "Подвійна нагорода за повідомлення з чату на 1 годину",
        "emoji":    E_STAR,
        "duration": 3600,
        "price_key":"shop_xp_boost_price",
        "default":  2000,
    },
    {
        "id":       "lottery",
        "name":     "Лото-білет",
        "desc":     "Миттєво отримай випадковий приз",
        "emoji":    "🎟️",
        "duration": None,
        "price_key":"shop_lottery_price",
        "default":  500,
    },
    {
        "id":       "crime_pass",
        "name":     "Crime Pass",
        "desc":     "Зняти штраф-блок після провалу /crime",
        "emoji":    "🦹",
        "duration": None,
        "price_key":"shop_crime_pass_price",
        "default":  3000,
    },
]

def get_item_price(eco: dict, item: dict) -> int:
    return eco.get(item["price_key"], item["default"])

# ── Embed магазину ─────────────────────────────────────────────────────────────

def build_shop_embed(eco: dict, guild: discord.Guild) -> discord.Embed:
    curr = eco.get("currency_emoji", E_COIN)
    E_SHOP_ICON = "<:shop:1479222993027727564>"
    embed = discord.Embed(
        title=f"{E_SHOP_ICON}  Магазин сервера",
        color=COLOR
    )
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

    for i, item in enumerate(SYSTEM_ITEMS, 1):
        price = get_item_price(eco, item)
        if price <= 0:
            continue
        dur_str = ""
        if item["duration"]:
            h = item["duration"] // 3600
            dur_str = f" • `{h}г`"
        embed.add_field(
            name=f"{item['emoji']}  {item['name']}",
            value=(
                f"{item['desc']}{dur_str}\n"
                f"**{price:,}** {curr}"
            ),
            inline=True
        )

    shop_roles = eco.get("shop_roles", [])
    if shop_roles:
        embed.add_field(name="\u200b", value="**🎭 Кастомні Ролі**", inline=False)
        for r in shop_roles:
            role_obj = guild.get_role(r["role_id"])
            if not role_obj: continue
            
            embed.add_field(
                name=f"🎭 {role_obj.name}",
                value=f"Купити роль назавжди\n**{r['price']:,}** {curr}",
                inline=True
            )

    embed.set_footer(text="Обери предмет кнопкою нижче")
    return embed

# ── View з кнопками купівлі ───────────────────────────────────────────────────

class ShopView(discord.ui.View):
    def __init__(self, eco: dict, guild_id: int, user: discord.Member):
        super().__init__(timeout=120)
        self.eco      = eco
        self.guild_id = guild_id
        self.user     = user
        curr          = eco.get("currency_emoji", E_COIN)

        for item in SYSTEM_ITEMS:
            price = get_item_price(eco, item)
            if price <= 0:
                continue
            btn = discord.ui.Button(
                label=f"{item['name']} — {price:,}",
                emoji=discord.PartialEmoji.from_str(item["emoji"]) if "<:" in item["emoji"] else item["emoji"],
                style=discord.ButtonStyle.secondary,
                custom_id=f"buy_{item['id']}"
            )
            btn.callback = self._make_buy_callback(item)
            self.add_item(btn)

        shop_roles = eco.get("shop_roles", [])
        for r in shop_roles:
            btn = discord.ui.Button(
                label=f"Роль — {r['price']:,}",
                emoji="🎭",
                style=discord.ButtonStyle.secondary,
                custom_id=f"buy_role_{r['role_id']}"
            )
            btn.callback = self._make_role_callback(r)
            self.add_item(btn)

    def _make_buy_callback(self, item: dict):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message(f"{E_CROSS} Це не твій магазин!", ephemeral=True)
                return

            eco   = self.eco
            curr  = eco.get("currency_emoji", E_COIN)
            price = get_item_price(eco, item)

            user_data = await get_user(db, self.guild_id, interaction.user.id)
            wallet    = user_data.get("wallet", 0)

            if wallet < price:
                await interaction.response.send_message(
                    f"{E_CROSS} Недостатньо коштів. Баланс: **{wallet:,}** {curr}, потрібно **{price:,}** {curr}.",
                    ephemeral=True
                )
                return

            now = int(time.time())

            # ── Логіка кожного предмета ──
            if item["id"] == "shield":
                until = now + item["duration"]
                await db.users.update_one(
                    {"guild_id": self.guild_id, "user_id": interaction.user.id},
                    {
                        "$inc": {"wallet": -price},
                        "$set": {"shield_until": until},
                        "$push": {"eco_history": {"$each": [{"log": f"🔴 **{price}** | Купівля: Щит | <t:{now}:t>"}], "$slice": -10}}
                    }
                )
                desc = f"{item['emoji']} **Щит** активний до <t:{until}:t>"

            elif item["id"] == "coin_boost":
                until = now + item["duration"]
                await db.users.update_one(
                    {"guild_id": self.guild_id, "user_id": interaction.user.id},
                    {
                        "$inc": {"wallet": -price},
                        "$set": {"coin_boost_until": until},
                        "$push": {"eco_history": {"$each": [{"log": f"ട **{price}** | Купівля: Coin Буст | <t:{now}:t>"}], "$slice": -10}}
                    }
                )
                desc = f"{item['emoji']} **Coin Буст** активний до <t:{until}:t>"

            elif item["id"] == "lottery":
                prizes  = [50,  100, 200, 400,  800, 2000]
                weights = [35,  30,  20,  10,   4,   1   ]
                prize = random.choices(prizes, weights=weights, k=1)[0]
                await db.users.update_one(
                    {"guild_id": self.guild_id, "user_id": interaction.user.id},
                    {
                        "$inc": {"wallet": prize - price, "total_earned": prize},
                        "$push": {"eco_history": {"$each": [{"log": f"🟢 **{prize}** | Лото виграш | <t:{now}:t>"}], "$slice": -10}}
                    }
                )
                desc = f"🎟️ Твій виграш: **{prize:,}** {curr}!"

            elif item["id"] == "crime_pass":
                await db.users.update_one(
                    {"guild_id": self.guild_id, "user_id": interaction.user.id},
                    {
                        "$inc": {"wallet": -price},
                        "$unset": {"crime_ban_until": ""},
                        "$push": {"eco_history": {"$each": [{"log": f"🔴 **{price}** | Купівля: Crime Pass | <t:{now}:t>"}], "$slice": -10}}
                    }
                )
                desc = "🦹 Штраф-блок знятий. /crime знову доступний."
            else:
                desc = f"{E_CHECK} Придбано **{item['name']}**"

            embed = discord.Embed(
                title=f"{E_CHECK}  Успішна покупка",
                description=f"{desc}\n\nСплачено: **{price:,}** {curr}",
                color=0x57f287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        return callback

    def _make_role_callback(self, role_info: dict):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message(f"{E_CROSS} Це не твій магазин!", ephemeral=True)
                return

            eco   = self.eco
            curr  = eco.get("currency_emoji", E_COIN)
            price = role_info["price"]
            role_id = role_info["role_id"]

            user_data = await get_user(db, self.guild_id, interaction.user.id)
            wallet    = user_data.get("wallet", 0)

            if wallet < price:
                await interaction.response.send_message(
                    f"{E_CROSS} Недостатньо коштів. Баланс: **{wallet:,}** {curr}, потрібно **{price:,}** {curr}.",
                    ephemeral=True
                )
                return

            inv_roles = user_data.get("inventory_roles", [])
            if role_id in inv_roles or any(r.id == role_id for r in interaction.user.roles):
                await interaction.response.send_message(f"{E_CROSS} Ця роль вже є у тебе!", ephemeral=True)
                return

            role_obj = interaction.guild.get_role(role_id)
            if role_obj:
                try:
                    await interaction.user.add_roles(role_obj, reason="Купівля в магазині")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        f"{E_CROSS} У бота немає прав на видачу ролі {role_obj.name}! Покупку скасовано.",
                        ephemeral=True
                    )
                    return
                except discord.HTTPException:
                    pass

            now = int(time.time())
            await db.users.update_one(
                {"guild_id": self.guild_id, "user_id": interaction.user.id},
                {
                    "$inc": {"wallet": -price},
                    "$addToSet": {"inventory_roles": role_id},
                    "$push": {"eco_history": {"$each": [{"log": f"🔴 **{price}** | Купівля ролі | <t:{now}:t>"}], "$slice": -10}}
                }
            )

            embed = discord.Embed(
                title=f"{E_CHECK}  Успішна покупка",
                description=f"🎭 Придбано роль {role_obj.mention if role_obj else 'Unknown Role'}\n\nСплачено: **{price:,}** {curr}",
                color=0x57f287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        return callback

# ── /inventory embed ──────────────────────────────────────────────────────────

async def build_inventory_embed(user: discord.Member, guild_id: int, eco: dict) -> discord.Embed:
    user_data = await get_user(db, guild_id, user.id)
    curr      = eco.get("currency_emoji", E_COIN)
    now       = int(time.time())

    embed = discord.Embed(
        title=f"<:inbox:1479128004847341620>  Інвентар — {user.display_name}",
        color=COLOR
    )

    items_found = False

    shield = user_data.get("shield_until", 0)
    if shield and shield > now:
        embed.add_field(name=f"{E_SHIELD} Щит", value=f"Активний до <t:{shield}:R>", inline=True)
        items_found = True
    
    xpb = user_data.get("xp_boost_until", 0)
    if xpb and xpb > now:
        embed.add_field(name=f"{E_STAR} XP Буст", value=f"Активний до <t:{xpb}:R>", inline=True)
        items_found = True
    
    cb = user_data.get("crime_ban_until", 0)
    if cb and cb > now:
        embed.add_field(name="⛔ Розслідування", value=f"Знімається <t:{cb}:R>", inline=True)
        items_found = True
    
    inv_roles = user_data.get("inventory_roles", [])
    if inv_roles:
        roles_txt = "\n".join(f"<@&{r}>" for r in inv_roles)
        embed.add_field(name="🎭 Куплені ролі", value=roles_txt, inline=False)
        items_found = True

    if not items_found:
        embed.description = "*Інвентар порожній*"

    return embed

# ── Cog ───────────────────────────────────────────────────────────────────────

class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Переглянути магазин сервера та купити предмети")
    async def shop(self, interaction: discord.Interaction):
        settings = await db.guild_settings.find_one({"_id": interaction.guild.id}) or {}
        eco      = get_eco(settings)

        if not eco.get("enabled", True):
            await interaction.response.send_message(f"{E_CROSS} Економіка вимкнена.", ephemeral=True)
            return

        embed = build_shop_embed(eco, interaction.guild)
        view  = ShopView(eco, interaction.guild.id, interaction.user)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ShopCog(bot))
