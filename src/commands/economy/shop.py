from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import time
import random

from modules.db import get_database
from repositories.user import get_user
from commands.administration.economy_setup import get_eco
from utils.ui_contract import add_section, gameplay_result_embed, set_surface_footer, surface_embed

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
        "price_key":"shop_shield_price",
        "default":  5000,
    },
    {
        "id":       "coin_boost",
        "name":     "Coin Буст",
        "desc":     "Подвійна нагорода за повідомлення з чату на 1 годину",
        "emoji":    E_STAR,
        "price_key":"shop_xp_boost_price",
        "default":  2000,
    },
    {
        "id":       "lootbox_common",
        "name":     "Звичайний Лутбокс",
        "desc":     "Може містити монети, предмети або невеликі бонуси",
        "emoji":    "<:openlootbox:1479952212980535498>",
        "price_key":"shop_lootbox_common_price",
        "default":  2500,
    },
    {
        "id":       "lootbox_rare",
        "name":     "Рідкісний Лутбокс",
        "desc":     "Цінний дроп, багато монет або унікальні ролі",
        "emoji":    "<:gifttop:1479952511635820586>",
        "price_key":"shop_lootbox_rare_price",
        "default":  10000,
    },
    {
        "id":       "crime_pass",
        "name":     "Crime Pass",
        "desc":     "Може зняти штраф-блок після провалу /crime",
        "emoji":    "<:crimepass:1479951455543889970>",
        "price_key":"shop_crime_pass_price",
        "default":  3000,
    },
]

ITEMS_REGISTRY = {item["id"]: item for item in SYSTEM_ITEMS}

def get_item_price(eco: dict, item: dict) -> int:
    return eco.get(item["price_key"], item["default"])

# ── Embed магазину ─────────────────────────────────────────────────────────────

def build_shop_embed(eco: dict, guild: discord.Guild) -> discord.Embed:
    curr = eco.get("currency_emoji", E_COIN)
    E_SHOP_ICON = "<:shop:1479222993027727564>"
    embed = surface_embed(
        "gameplay",
        title=f"{E_SHOP_ICON}  Магазин сервера",
        description="Спочатку подивіться асортимент, потім оберіть предмет кнопкою нижче. Деталі покупки приходять окремим результатом.",
    )
    embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

    system_lines = []
    for i, item in enumerate(SYSTEM_ITEMS, 1):
        price = get_item_price(eco, item)
        if price <= 0:
            continue
        system_lines.append(f"{item['emoji']} **{item['name']}** — `{price:,}` {curr}\n{item['desc']}")
    if system_lines:
        add_section(embed, "Системні предмети", system_lines, inline=False)

    shop_roles = eco.get("shop_roles", [])
    if shop_roles:
        role_lines = []
        for r in shop_roles:
            role_obj = guild.get_role(r["role_id"])
            if not role_obj:
                continue
            role_lines.append(f"🎭 **{role_obj.name}** — `{r['price']:,}` {curr}\nКупити роль назавжди")
        if role_lines:
            add_section(embed, "Кастомні ролі", role_lines, inline=False)

    set_surface_footer(embed, "gameplay", "Оберіть предмет кнопкою нижче.")
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

            now = int(time.time())

            log_entry = {"log": f"🔴 **{price}** | Придбано: {item['name']} | <t:{now}:t>"}
            result = await db.users.find_one_and_update(
                {"guild_id": self.guild_id, "user_id": interaction.user.id, "wallet": {"$gte": price}},
                {
                    "$inc": {"wallet": -price},
                    "$push": {"eco_history": {"$each": [log_entry], "$slice": -50}}
                }
            )
            
            if not result:
                await interaction.response.send_message(
                    f"{E_CROSS} Недостатньо коштів або під час обробки ви вже витратили їх. Баланс: **{wallet:,}** {curr}, потрібно **{price:,}** {curr}.",
                    ephemeral=True
                )
                return

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, interaction.user.id)

            await db.inventory.update_one(
                {"guild_id": self.guild_id, "user_id": interaction.user.id},
                {"$inc": {f"items.{item['id']}": 1}},
                upsert=True
            )
            
            desc = f"{E_CHECK} Ви успішно купили **{item['name']}**.\n*Цей предмет відправлено до вашого Інвентарю (/economy).*"

            embed = gameplay_result_embed(
                f"{E_CHECK}  Успішна покупка",
                f"{desc}\n\nСплачено: **{price:,}** {curr}",
                tone="success",
                footer="Предмет уже в інвентарі або готовий до використання.",
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

            if inv_roles and role_id in inv_roles or any(r.id == role_id for r in interaction.user.roles):
                await interaction.response.send_message(f"{E_CROSS} Ця роль вже є у тебе!", ephemeral=True)
                return

            role_obj = interaction.guild.get_role(role_id)
            if not role_obj:
                return await interaction.response.send_message(f"{E_CROSS} Роль більше не існує на сервері.", ephemeral=True)

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

            log_entry = {"log": f"🔴 **{price}** | Купівля ролі | <t:{now}:t>"}
            result = await db.users.find_one_and_update(
                {"guild_id": self.guild_id, "user_id": interaction.user.id, "wallet": {"$gte": price}},
                {
                    "$inc": {"wallet": -price},
                    "$addToSet": {"inventory_roles": role_id},
                    "$push": {"eco_history": {"$each": [log_entry], "$slice": -50}}
                }
            )

            if not result:
                try:
                    await interaction.user.remove_roles(role_obj, reason="Недостатньо коштів (Race Condition Guard)")
                except:
                    pass
                return await interaction.response.send_message(
                    f"{E_CROSS} Недостатньо коштів! Баланс: **{wallet:,}** {curr}, потрібно **{price:,}** {curr}.",
                    ephemeral=True
                )

            from modules.db import invalidate_user_data
            await invalidate_user_data(interaction.guild.id, interaction.user.id)

            embed = gameplay_result_embed(
                f"{E_CHECK}  Успішна покупка",
                f"🎭 Придбано роль {role_obj.mention if role_obj else 'Unknown Role'}\n\nСплачено: **{price:,}** {curr}",
                tone="success",
                footer="Роль видана одразу після списання коштів.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        return callback

# ── /inventory embed та логіка ────────────────────────────────────────────────

async def build_inventory_embed_and_view(user: discord.Member, guild_id: int, eco: dict, main_eco_view=None):
    
    user_data = await get_user(db, guild_id, user.id)
    curr      = eco.get("currency_emoji", E_COIN)
    now       = int(time.time())

    embed = surface_embed(
        "gameplay",
        title=f"<:inbox:1479128004847341620>  Інвентар — {user.display_name}",
        description="Тут зібрані активні бонуси, предмети та ролі, які вже були куплені.",
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

    inv_data = await db.inventory.find_one({"guild_id": guild_id, "user_id": user.id}) or {}
    items_dict = inv_data.get("items", {}) 
    
    available_items = {k: v for k, v in items_dict.items() if isinstance(v, int) and v > 0}
    
    if available_items:
        items_found = True
        desc_lines = []
        for i_id, count in available_items.items():
            reg = ITEMS_REGISTRY.get(i_id)
            if reg:
                desc_lines.append(f"{reg['emoji']} **{reg['name']}**: `{count}` шт.")
            else:
                desc_lines.append(f"<:openlootbox:1479952212980535498> **Невідомий предмет ({i_id})**: `{count}` шт.")
        
        embed.add_field(name="🎒 Ваша сумка", value="\n".join(desc_lines), inline=False)

    if not items_found:
        embed.description = "*Тут порожньо. Завітайте до Магазину!*"
    set_surface_footer(embed, "gameplay", "Активні бафи показуються окремо від предметів у сумці.")
        
    view = InventoryView(user.id, guild_id, eco, available_items, main_eco_view)
    return embed, view

class InventorySelect(discord.ui.Select):
    def __init__(self, available_items: dict):
        options = []
        for i_id, count in available_items.items():
            reg = ITEMS_REGISTRY.get(i_id)
            if reg:
                options.append(discord.SelectOption(
                    label=f"{reg['name']} (x{count})",
                    value=i_id,
                    emoji=discord.PartialEmoji.from_str(reg["emoji"]) if "<:" in reg["emoji"] else reg["emoji"],
                    description=reg.get("desc", "")[:50]
                ))
                
        super().__init__(placeholder="Оберіть предмет для використання...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        item_id = self.values[0]
        count = self.view.available_items.get(item_id, 0)
        reg = ITEMS_REGISTRY.get(item_id)
        
        if not reg or count <= 0:
            return await interaction.response.send_message(f"{E_CROSS} Помилка предмета.", ephemeral=True)
            
        embed = discord.Embed(
            title=f"Використання: {reg['name']}",
            description=f"У вас є: **{count}** шт.\n\n{reg['desc']}",
            color=COLOR
        )
        
        await interaction.response.edit_message(embed=embed, view=ItemActionView(self.view, item_id, count, reg))

class InventoryView(discord.ui.View):
    def __init__(self, owner_id: int, guild_id: int, eco: dict, available_items: dict, main_eco_view=None):
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.eco = eco
        self.available_items = available_items
        self.main_eco_view = main_eco_view
        
        if available_items:
            self.add_item(InventorySelect(available_items))
            
        btn_back = discord.ui.Button(label="Назад в Економіку", style=discord.ButtonStyle.secondary, emoji="◀️")
        btn_back.callback = self._back_cb
        self.add_item(btn_back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("<:cutiex:1480246146076119132> Це не твій інвентар!", ephemeral=True)
            return False
        return True

    async def _back_cb(self, interaction: discord.Interaction):
        if self.main_eco_view:
            from commands.economy.economy import build_economy_embed
            user_data = await get_user(db, self.guild_id, interaction.user.id)
            embed = build_economy_embed(interaction.user, user_data, self.eco)
            await interaction.response.edit_message(embed=embed, view=self.main_eco_view)
        else:
            await interaction.response.edit_message(content="Меню закрито.", embed=None, view=None)

class ItemActionView(discord.ui.View):
    def __init__(self, parent_view: InventoryView, item_id: str, max_count: int, reg: dict):
        super().__init__(timeout=900)
        self.parent_view = parent_view
        self.item_id = item_id
        self.max_count = max_count
        self.reg = reg
        
        action_name = "Відкрити" if "lootbox" in item_id else "Використати"
        
        btn_one = discord.ui.Button(label=f"{action_name} 1 шт.", style=discord.ButtonStyle.success)
        btn_one.callback = self._use_one
        self.add_item(btn_one)
        
        if max_count > 1:
            btn_all = discord.ui.Button(label=f"{action_name} всі ({max_count})", style=discord.ButtonStyle.primary)
            btn_all.callback = self._use_all
            self.add_item(btn_all)
            
        btn_back = discord.ui.Button(label="Назад", style=discord.ButtonStyle.secondary, emoji="◀️")
        btn_back.callback = self._back
        self.add_item(btn_back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.parent_view.interaction_check(interaction)

    async def _back(self, interaction: discord.Interaction):
        
        embed, view = await build_inventory_embed_and_view(
            interaction.user, self.parent_view.guild_id, self.parent_view.eco, self.parent_view.main_eco_view
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _use_one(self, interaction: discord.Interaction):
        await self._process_use(interaction, 1)

    async def _use_all(self, interaction: discord.Interaction):
        await self._process_use(interaction, self.max_count)

    async def _process_use(self, interaction: discord.Interaction, amount: int):
        
        inv_data = await db.inventory.find_one({"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id}) or {}
        items_dict = inv_data.get("items", {})
        
        actual_count = items_dict.get(self.item_id, 0)
        if actual_count < amount:
            return await interaction.response.send_message(f"{E_CROSS} У вас недостатньо цього предмета!", ephemeral=True)
            
        await db.inventory.update_one(
            {"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id},
            {"$inc": {f"items.{self.item_id}": -amount}}
        )
        
        now = int(time.time())
        curr = self.parent_view.eco.get("currency_emoji", E_COIN)
        
        is_lootbox = "lootbox" in self.item_id
        if is_lootbox:
            await interaction.response.edit_message(
                embed=discord.Embed(title="Відкриваємо...", description=f"<:openlootbox:1479952212980535498> {self.reg['name']} x{amount}...\n\n*Триває розпакування...*", color=discord.Color.gold()),
                view=None
            )
            import asyncio
            for step in ["⚡", "<:firecracker:1479953348185555077>", "✨"]:
                await asyncio.sleep(1)
                await interaction.edit_original_response(
                    embed=discord.Embed(title="Відкриваємо...", description=f"{step} {self.reg['name']} x{amount}...\n\n*Триває розпакування...*", color=discord.Color.gold())
                )
            await asyncio.sleep(0.5)
            
        results = []
        total_coins = 0
        
        for _ in range(amount):
            if self.item_id == "shield":
                await db.users.update_one(
                    {"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id},
                    {"$set": {"shield_until": now + 86400}}
                )
                results.append("🛡️ Активовано Щит на 24 години.")
            
            elif self.item_id == "coin_boost":
                await db.users.update_one(
                    {"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id},
                    {"$set": {"xp_boost_until": now + 3600}}
                )
                results.append(f"⭐ Активовано Coin Буст на 1 годину.")
                
            elif self.item_id == "crime_pass":
                user_u = await get_user(db, self.parent_view.guild_id, interaction.user.id)
                if user_u.get("crime_ban_until", 0) > now:
                    await db.users.update_one(
                        {"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id},
                        {"$unset": {"crime_ban_until": ""}}
                    )
                    results.append("<:crimepass:1479951455543889970> Знято обмеження розслідування /crime.")
                else:
                    results.append("<:crimepass:1479951455543889970> Обмежень не було знайдено (витрачено дарма).")
                    
            elif self.item_id == "lootbox_common":
                opts = [
                    (500, 1500, "coins", 70),
                    (0, 0, "shield", 20),
                    (2000, 4000, "coins", 10)
                ]
                win = random.choices(opts, weights=[x[3] for x in opts], k=1)[0]
                if win[2] == "coins":
                    c = random.randint(win[0], win[1])
                    total_coins += c
                    results.append(f"🟢 +{c:,} монет")
                else:
                    await db.inventory.update_one(
                        {"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id},
                        {"$inc": {"items.shield": 1}},
                        upsert=True
                    )
                    results.append(f"🛡️ Отримано Щит (в інвентар)")
                    
            elif self.item_id == "lootbox_rare":
                opts = [
                    (5000, 12000, "coins", 60),
                    (0, 0, "coin_boost", 25),
                    (0, 0, "crime_pass", 10),
                    (20000, 50000, "coins", 5)
                ]
                win = random.choices(opts, weights=[x[3] for x in opts], k=1)[0]
                if win[2] == "coins":
                    c = random.randint(win[0], win[1])
                    total_coins += c
                    results.append(f"🟢 +{c:,} монет")
                elif win[2] == "coin_boost":
                    await db.inventory.update_one(
                        {"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id},
                        {"$inc": {"items.coin_boost": 1}},
                        upsert=True
                    )
                    results.append(f"⭐ Отримано Coin Буст (в інвентар)")
                else:
                    await db.inventory.update_one(
                        {"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id},
                        {"$inc": {"items.crime_pass": 1}},
                        upsert=True
                    )
                    results.append(f"<:crimepass:1479951455543889970> Отримано Crime Pass (в інвентар)")
                    
        if total_coins > 0:
            await db.users.update_one(
                {"guild_id": self.parent_view.guild_id, "user_id": interaction.user.id},
                {
                    "$inc": {"wallet": total_coins},
                    "$push": {"eco_history": {"$each": [{"log": f"🟢 **{total_coins}** | Лутбокс дроп | <t:{now}:t>"}], "$slice": -50}}
                }
            )
            
        log_res = "\n".join(results[:15])
        if len(results) > 15:
            log_res += f"\n*...та ще {len(results)-15} предметів*"
            
        if total_coins > 0:
            log_res += f"\n\n<:Coins:1478486725113286899> **Загалом монет:** {total_coins:,} {curr}"
            
        embed = discord.Embed(
            title=f"{E_CHECK} Успішно ({self.reg['name']} x{amount})",
            description=log_res,
            color=0x57f287 if is_lootbox else COLOR
        )
        
        view_back = discord.ui.View()
        btn_back = discord.ui.Button(label="Повернутися до Інвентарю", style=discord.ButtonStyle.secondary, emoji="🎒")
        
        async def _back_to_inv(i: discord.Interaction):
            emb, vw = await build_inventory_embed_and_view(i.user, self.parent_view.guild_id, self.parent_view.eco, self.parent_view.main_eco_view)
            await i.response.edit_message(embed=emb, view=vw)
            
        btn_back.callback = _back_to_inv
        view_back.add_item(btn_back)
        
        if is_lootbox:
            await interaction.edit_original_response(embed=embed, view=view_back)
        else:
            await interaction.response.edit_message(embed=embed, view=view_back)

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
