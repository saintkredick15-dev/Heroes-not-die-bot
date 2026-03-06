import discord
from discord.ext import commands, tasks
import time
import datetime
from modules.db import get_database
from repositories.user import get_user
from commands.administration.economy_setup import get_eco

db = get_database()

RANK_BADGES = {1: "🥇", 2: "🥈", 3: "🥉"}

class SchedulerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.economy_scheduler.start()

    def cog_unload(self):
        self.economy_scheduler.cancel()

    @tasks.loop(minutes=10)
    async def economy_scheduler(self):
        """Головний цикл перевірки (кожні 10 хвилин)"""
        now = int(time.time())
        dt = datetime.datetime.fromtimestamp(now)
        today_str = dt.strftime("%Y-%m-%d")
        
        # Перебираємо всі сервери
        async for gd in db.guild_settings.find({}):
            guild_id = gd.get("_id")
            eco = get_eco(gd)
            
            if not eco.get("enabled", True):
                continue

            scheduler_state = gd.get("scheduler_state", {})
            updates = {}

            # 1. Скидання week_earned і xp_week (Щопонеділка)
            if dt.weekday() == 0 and scheduler_state.get("last_weekly_reset") != today_str:
                await db.users.update_many({"guild_id": guild_id}, {"$set": {"week_earned": 0, "xp_week": 0}})
                updates["scheduler_state.last_weekly_reset"] = today_str

            # 2. Скидання month_earned і xp_month (1-го числа)
            if dt.day == 1 and scheduler_state.get("last_monthly_reset") != today_str:
                await db.users.update_many({"guild_id": guild_id}, {"$set": {"month_earned": 0, "xp_month": 0}})
                updates["scheduler_state.last_monthly_reset"] = today_str

            # 3. Банківський відсоток
            interest_rate = eco.get("bank_interest_rate", 0.0)
            if interest_rate > 0:
                interval = eco.get("bank_interest_interval", "daily")
                can_apply = False
                
                if interval == "daily" and scheduler_state.get("last_bank_interest") != today_str:
                    can_apply = True
                elif interval == "weekly" and dt.weekday() == 0 and scheduler_state.get("last_bank_interest") != today_str:
                    can_apply = True

                if can_apply:
                    # Нараховуємо відсотки (bank *= (1 + rate / 100))
                    # Для цього беремо всіх юзерів з bank > 0 на цьому сервері
                    async for u in db.users.find({"guild_id": guild_id, "bank": {"$gt": 0}}):
                        bank = u.get("bank", 0)
                        profit = int(bank * (interest_rate / 100))
                        if profit > 0:
                            await db.users.update_one(
                                {"_id": u["_id"]},
                                {
                                    "$inc": {"bank": profit, "total_earned": profit},
                                    "$push": {"eco_history": {"$each": [{"log": f"🟢 **{profit}** | Банківські відсотки | <t:{now}:t>"}], "$slice": -50}}
                                }
                            )
                    updates["scheduler_state.last_bank_interest"] = today_str

            # 4. Перевірка на Season Reset
            season_duration = eco.get("season_duration_days", 30)
            season_start = eco.get("season_start", 0)
            if season_duration > 0 and season_start > 0:
                if now > season_start + (season_duration * 86400):
                    if updates:
                        await db.guild_settings.update_one({"_id": guild_id}, {"$set": updates})
                    await self.trigger_season_end(guild_id, eco, gd)
                    continue

            if updates:
                await db.guild_settings.update_one({"_id": guild_id}, {"$set": updates})

    @economy_scheduler.before_loop
    async def before_scheduler(self):
        await self.bot.wait_until_ready()

    async def trigger_season_end(self, guild_id: int, eco: dict, gd: dict):
        guild = self.bot.get_guild(guild_id)
        await perform_season_reset(guild, eco=eco, gd=gd)


async def perform_season_reset(guild: discord.Guild, eco: dict = None, gd: dict = None):
    """Публічна функція скидання сезону. Викликається з economy_setup або scheduler."""
    guild_id = guild.id
    now = int(time.time())

    if gd is None:
        gd = await db.guild_settings.find_one({"_id": guild_id}) or {}
    if eco is None:
        eco = get_eco(gd)

    season_num = eco.get("season_number", 1)
    curr = eco.get("currency_emoji", "🪙")
    curr_name = eco.get("currency_name", "Coin")

    # 1. Знайти топ 3 гравців (за wallet + bank)
    users = await db.users.find({"guild_id": guild_id}).to_list(length=None)
    users.sort(key=lambda x: x.get("wallet", 0) + x.get("bank", 0), reverse=True)
    top3 = users[:3]

    top3_data = []
    for i, u in enumerate(top3):
        total = u.get("wallet", 0) + u.get("bank", 0)
        if total > 0:
            top3_data.append({"user_id": u["user_id"], "earned": total})

    # 2. Зберегти у season_history
    history = gd.get("season_history", [])
    history.append({
        "season": season_num,
        "date": now,
        "top3": top3_data
    })

    # 3. Видати роль переможцям та забрати у минулих
    winner_role_id = eco.get("season_winner_role_id", 0)
    if winner_role_id > 0 and guild:
        role = guild.get_role(winner_role_id)
        if role:
            for m in role.members:
                try:
                    await m.remove_roles(role)
                except:
                    pass
            for t_data in top3_data:
                m = guild.get_member(t_data["user_id"])
                if m:
                    try:
                        await m.add_roles(role)
                    except:
                        pass

    # 4. Скинути баланс та видати стартовий бонус
    start_bonus = eco.get("season_start_bonus", 0)
    await db.users.update_many(
        {"guild_id": guild_id},
        {
            "$set": {
                "wallet": start_bonus,
                "bank": 0,
                "total_earned": start_bonus,
                "week_earned": 0,
                "month_earned": 0,
                "eco_history": []
            }
        }
    )

    # 5. Оновити налаштування сезону
    eco["season_start"] = now
    eco["season_number"] = season_num + 1
    await db.guild_settings.update_one(
        {"_id": guild_id},
        {"$set": {"economy": eco, "season_history": history}}
    )

    # 6. Опублікувати підсумок сезону в канал
    announce_channel_id = eco.get("season_announce_channel_id", 0)
    channel = None
    if announce_channel_id and guild:
        channel = guild.get_channel(announce_channel_id)
    if channel is None and guild:
        # Спробуємо знайти перший текстовий канал де бот може писати
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                channel = ch
                break

    if channel:
        embed = discord.Embed(
            title=f"🏆 Сезон {season_num} завершено!",
            description=f"Розпочинається **Сезон {season_num + 1}**!\n\n"
                        f"{'▸ Стартовий бонус: `' + str(start_bonus) + '` ' + curr if start_bonus > 0 else ''}",
            color=0xFFD700
        )
        lines = []
        for i, t_data in enumerate(top3_data, start=1):
            badge = RANK_BADGES.get(i, f"`{i}.`")
            member = guild.get_member(t_data["user_id"])
            name = member.mention if member else f"<@{t_data['user_id']}>"
            earned = t_data["earned"]
            lines.append(f"{badge} {name} — `{earned:,}` {curr}")
        if lines:
            embed.add_field(name="Топ гравців сезону", value="\n".join(lines), inline=False)
        embed.set_footer(text=f"Сезон завершено {datetime.datetime.fromtimestamp(now).strftime('%d.%m.%Y')}")
        try:
            await channel.send(embed=embed)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(SchedulerCog(bot))
