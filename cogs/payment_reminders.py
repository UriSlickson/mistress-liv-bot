"""
Payment Reminders Cog - Automatic reminders for unpaid wagers
- Daily reminders in #wagers channel
- Every 2 days DM to the person who owes
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime, timedelta
import logging
from typing import Optional

logger = logging.getLogger('MistressLIV.PaymentReminders')

# Team names for display
TEAM_NAMES = {
    'ARI': 'Cardinals', 'ATL': 'Falcons', 'BAL': 'Ravens', 'BUF': 'Bills',
    'CAR': 'Panthers', 'CHI': 'Bears', 'CIN': 'Bengals', 'CLE': 'Browns',
    'DAL': 'Cowboys', 'DEN': 'Broncos', 'DET': 'Lions', 'GB': 'Packers',
    'HOU': 'Texans', 'IND': 'Colts', 'JAX': 'Jaguars', 'KC': 'Chiefs',
    'LAC': 'Chargers', 'LAR': 'Rams', 'LV': 'Raiders', 'MIA': 'Dolphins',
    'MIN': 'Vikings', 'NE': 'Patriots', 'NO': 'Saints', 'NYG': 'Giants',
    'NYJ': 'Jets', 'PHI': 'Eagles', 'PIT': 'Steelers', 'SEA': 'Seahawks',
    'SF': '49ers', 'TB': 'Buccaneers', 'TEN': 'Titans', 'WAS': 'Commanders'
}


class PaymentRemindersCog(commands.Cog):
    """Cog for automatic payment reminders on unpaid wagers."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_reminder_table()
        
    def _ensure_reminder_table(self):
        """Ensure the reminder tracking table exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table to track when reminders were last sent
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wager_reminders (
                wager_id INTEGER PRIMARY KEY,
                last_dm_sent TEXT,
                last_channel_sent TEXT,
                dm_count INTEGER DEFAULT 0,
                channel_count INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    async def cog_load(self):
        """Called when the cog is loaded."""
        self.daily_channel_reminder.start()
        self.dm_reminder_check.start()
        logger.info("Payment reminders tasks started (daily channel, 2-day DM)")
    
    async def cog_unload(self):
        """Called when the cog is unloaded."""
        self.daily_channel_reminder.cancel()
        self.dm_reminder_check.cancel()
        logger.info("Payment reminders tasks stopped")
    
    def get_unpaid_wagers(self):
        """Get all settled but unpaid wagers with loser information."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Ensure the reminder table exists
        self._ensure_reminder_table()
        
        try:
            cursor.execute('''
                SELECT w.wager_id, w.season_year, w.week, w.home_team_id, w.away_team_id,
                       w.home_user_id, w.away_user_id, w.amount, w.winner_user_id,
                       w.winner_team_id, w.created_at,
                       r.last_dm_sent, r.last_channel_sent, r.dm_count, r.channel_count
                FROM wagers w
                LEFT JOIN wager_reminders r ON w.wager_id = r.wager_id
                WHERE w.winner_user_id IS NOT NULL 
                  AND (w.is_paid = 0 OR w.is_paid IS NULL)
                ORDER BY w.created_at ASC
            ''')
            
            wagers = cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching unpaid wagers: {e}")
            # Fallback: query without the reminders table
            cursor.execute('''
                SELECT w.wager_id, w.season_year, w.week, w.home_team_id, w.away_team_id,
                       w.home_user_id, w.away_user_id, w.amount, w.winner_user_id,
                       w.winner_team_id, w.created_at,
                       NULL, NULL, 0, 0
                FROM wagers w
                WHERE w.winner_user_id IS NOT NULL 
                  AND (w.is_paid = 0 OR w.is_paid IS NULL)
                ORDER BY w.created_at ASC
            ''')
            wagers = cursor.fetchall()
        
        conn.close()
        return wagers
    
    def get_loser_id(self, wager) -> Optional[int]:
        """Determine who lost the wager (the person who owes money)."""
        wager_id, season_year, week, home_team, away_team, home_user_id, away_user_id, amount, winner_user_id, winner_team_id, created_at, last_dm, last_channel, dm_count, channel_count = wager
        
        if winner_user_id == home_user_id:
            return away_user_id
        elif winner_user_id == away_user_id:
            return home_user_id
        else:
            return None
    
    def should_send_dm(self, last_dm_sent: Optional[str]) -> bool:
        """Check if 2 days have passed since the last DM reminder."""
        if last_dm_sent is None:
            return True
        
        try:
            last_sent = datetime.fromisoformat(last_dm_sent)
            time_since = datetime.now() - last_sent
            return time_since >= timedelta(days=2)
        except:
            return True
    
    def update_dm_sent(self, wager_id: int):
        """Update the last DM sent time for a wager."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO wager_reminders (wager_id, last_dm_sent, dm_count)
            VALUES (?, ?, 1)
            ON CONFLICT(wager_id) DO UPDATE SET
                last_dm_sent = excluded.last_dm_sent,
                dm_count = COALESCE(wager_reminders.dm_count, 0) + 1
        ''', (wager_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def update_channel_sent(self, wager_id: int):
        """Update the last channel reminder sent time for a wager."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO wager_reminders (wager_id, last_channel_sent, channel_count)
            VALUES (?, ?, 1)
            ON CONFLICT(wager_id) DO UPDATE SET
                last_channel_sent = excluded.last_channel_sent,
                channel_count = COALESCE(wager_reminders.channel_count, 0) + 1
        ''', (wager_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    async def get_wagers_channel(self, guild):
        """Find the #wagers channel."""
        for channel in guild.text_channels:
            if channel.name.lower() in ['wagers', 'wager-log', 'wager-logs']:
                return channel
        return None
    
    @tasks.loop(hours=24)  # Daily channel reminder
    async def daily_channel_reminder(self):
        """Post daily reminder in #wagers channel for all unpaid wagers."""
        await self.bot.wait_until_ready()
        
        logger.info("Running daily #wagers channel reminder...")
        
        unpaid_wagers = self.get_unpaid_wagers()
        
        if not unpaid_wagers:
            logger.info("No unpaid wagers found")
            return
        
        # Group wagers by loser
        by_loser = {}
        for wager in unpaid_wagers:
            wager_id, season_year, week, home_team, away_team, home_user_id, away_user_id, amount, winner_user_id, winner_team_id, created_at, last_dm, last_channel, dm_count, channel_count = wager
            
            loser_id = self.get_loser_id(wager)
            if loser_id is None:
                continue
            
            if loser_id not in by_loser:
                by_loser[loser_id] = {'wagers': [], 'total': 0}
            
            by_loser[loser_id]['wagers'].append({
                'wager_id': wager_id,
                'week': week,
                'home_team': home_team,
                'away_team': away_team,
                'amount': amount,
                'winner_id': winner_user_id
            })
            by_loser[loser_id]['total'] += amount
        
        # Post to #wagers channel in each guild
        for guild in self.bot.guilds:
            wagers_channel = await self.get_wagers_channel(guild)
            if not wagers_channel:
                continue
            
            # Create a summary embed
            embed = discord.Embed(
                title="📋 Daily Unpaid Wagers Summary",
                description=f"**{len(unpaid_wagers)}** unpaid wager(s) across **{len(by_loser)}** member(s)",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            # Add each debtor
            for loser_id, data in list(by_loser.items())[:15]:  # Limit to 15 to avoid embed limits
                try:
                    loser = await self.bot.fetch_user(loser_id)
                    loser_name = loser.mention if loser else f"<@{loser_id}>"
                except:
                    loser_name = f"<@{loser_id}>"
                
                wager_details = []
                for w in data['wagers'][:3]:  # Show up to 3 wagers per person
                    try:
                        winner = await self.bot.fetch_user(w['winner_id'])
                        winner_name = winner.display_name if winner else "Unknown"
                    except:
                        winner_name = "Unknown"
                    
                    home_name = TEAM_NAMES.get(w['home_team'], w['home_team'])
                    away_name = TEAM_NAMES.get(w['away_team'], w['away_team'])
                    wager_details.append(f"• ${w['amount']:.2f} → **{winner_name}** ({away_name} @ {home_name})")
                
                if len(data['wagers']) > 3:
                    wager_details.append(f"• ...and {len(data['wagers']) - 3} more")
                
                embed.add_field(
                    name=f"{loser_name} owes ${data['total']:.2f}",
                    value="\n".join(wager_details) if wager_details else "Details unavailable",
                    inline=False
                )
            
            if len(by_loser) > 15:
                embed.add_field(
                    name="...",
                    value=f"And {len(by_loser) - 15} more members with unpaid wagers",
                    inline=False
                )
            
            embed.set_footer(text="Use /paid to confirm payments | DM reminders sent every 2 days")
            
            try:
                await wagers_channel.send(embed=embed)
                logger.info(f"Posted daily wager summary to #{wagers_channel.name}")
                
                # Update channel sent tracking
                for wager in unpaid_wagers:
                    self.update_channel_sent(wager[0])  # wager_id
                    
            except discord.Forbidden:
                logger.warning(f"Could not post to #{wagers_channel.name}")
            except Exception as e:
                logger.error(f"Error posting daily reminder: {e}")
    
    @tasks.loop(hours=12)  # Check twice a day for 2-day DM reminders
    async def dm_reminder_check(self):
        """Check for unpaid wagers and send DM reminders every 2 days."""
        await self.bot.wait_until_ready()
        
        logger.info("Checking for DM reminders (every 2 days)...")
        
        unpaid_wagers = self.get_unpaid_wagers()
        
        if not unpaid_wagers:
            return
        
        # Group wagers by loser that need DM reminders
        reminders_to_send = {}
        
        for wager in unpaid_wagers:
            wager_id, season_year, week, home_team, away_team, home_user_id, away_user_id, amount, winner_user_id, winner_team_id, created_at, last_dm, last_channel, dm_count, channel_count = wager
            
            # Check if we should send a DM (2 days since last one)
            if not self.should_send_dm(last_dm):
                continue
            
            loser_id = self.get_loser_id(wager)
            if loser_id is None:
                continue
            
            if loser_id not in reminders_to_send:
                reminders_to_send[loser_id] = []
            
            reminders_to_send[loser_id].append({
                'wager_id': wager_id,
                'week': week,
                'home_team': home_team,
                'away_team': away_team,
                'amount': amount,
                'winner_id': winner_user_id,
                'dm_count': dm_count or 0
            })
        
        # Send DM reminders
        for loser_id, wagers in reminders_to_send.items():
            await self.send_dm_reminder(loser_id, wagers)
    
    async def send_dm_reminder(self, loser_id: int, wagers: list):
        """Send a DM reminder to the user who owes money."""
        try:
            user = await self.bot.fetch_user(loser_id)
            if user is None:
                logger.warning(f"Could not find user {loser_id}")
                return
            
            # Calculate total owed
            total_owed = sum(w['amount'] for w in wagers)
            
            # Build the DM reminder
            embed = discord.Embed(
                title="💰 Wager Payment Reminder",
                description=f"You have **{len(wagers)}** unpaid wager(s) totaling **${total_owed:.2f}**.",
                color=discord.Color.orange()
            )
            
            # Add details for each unpaid wager
            for w in wagers[:10]:  # Limit to 10
                try:
                    winner = await self.bot.fetch_user(w['winner_id'])
                    winner_name = winner.display_name if winner else "Unknown"
                except:
                    winner_name = "Unknown"
                
                home_name = TEAM_NAMES.get(w['home_team'], w['home_team'])
                away_name = TEAM_NAMES.get(w['away_team'], w['away_team'])
                
                reminder_num = w['dm_count'] + 1
                embed.add_field(
                    name=f"${w['amount']:.2f} owed to {winner_name}",
                    value=f"**{away_name} @ {home_name}** (Wk {w['week']})\n*DM Reminder #{reminder_num}*",
                    inline=True
                )
            
            if len(wagers) > 10:
                embed.add_field(
                    name="...",
                    value=f"And {len(wagers) - 10} more unpaid wagers",
                    inline=False
                )
            
            embed.add_field(
                name="How to Pay",
                value="Pay the winner directly, then have them use `/paid` to confirm.\nUse `/mywagers` to see all your wagers.",
                inline=False
            )
            
            embed.set_footer(text="DM reminders sent every 2 days | Daily reminders in #wagers")
            embed.timestamp = datetime.now()
            
            # Send DM
            try:
                await user.send(embed=embed)
                logger.info(f"Sent DM reminder to {user.display_name} for {len(wagers)} unpaid wagers (${total_owed:.2f})")
                
                # Update DM tracking for each wager
                for w in wagers:
                    self.update_dm_sent(w['wager_id'])
                    
            except discord.Forbidden:
                logger.warning(f"Could not DM user {user.display_name} - DMs disabled")
            except Exception as e:
                logger.error(f"Error sending DM to {user.display_name}: {e}")
                
        except Exception as e:
            logger.error(f"Error in send_dm_reminder for user {loser_id}: {e}")
    
    @daily_channel_reminder.before_loop
    async def before_daily_channel_reminder(self):
        """Wait for the bot to be ready."""
        await self.bot.wait_until_ready()
        logger.info("Daily channel reminder task is ready")
    
    @dm_reminder_check.before_loop
    async def before_dm_reminder_check(self):
        """Wait for the bot to be ready."""
        await self.bot.wait_until_ready()
        logger.info("DM reminder check task is ready")
    
    @app_commands.command(name="checkreminders", description="[Admin] Manually trigger payment reminder check")
    @app_commands.default_permissions(administrator=True)
    async def check_reminders(self, interaction: discord.Interaction):
        """Manually trigger a check for unpaid wagers and send reminders."""
        await interaction.response.defer(ephemeral=True)
        
        unpaid_wagers = self.get_unpaid_wagers()
        
        if not unpaid_wagers:
            await interaction.followup.send("✅ No unpaid wagers found!", ephemeral=True)
            return
        
        # Count unique losers
        losers = set()
        total_owed = 0
        for wager in unpaid_wagers:
            loser_id = self.get_loser_id(wager)
            if loser_id:
                losers.add(loser_id)
                total_owed += wager[7]  # amount is at index 7
        
        await interaction.followup.send(
            f"📊 **Unpaid Wagers Summary:**\n"
            f"• Total unpaid wagers: **{len(unpaid_wagers)}**\n"
            f"• Users with outstanding debts: **{len(losers)}**\n"
            f"• Total amount owed: **${total_owed:.2f}**\n\n"
            f"Running reminder checks now...",
            ephemeral=True
        )
        
        # Trigger both checks
        await self.daily_channel_reminder()
        await self.dm_reminder_check()
        
        await interaction.followup.send("✅ Reminder checks complete!", ephemeral=True)
    
    @app_commands.command(name="allunpaidwagers", description="[Admin] Show all unpaid wagers in the league")
    @app_commands.default_permissions(administrator=True)
    async def all_unpaid_wagers(self, interaction: discord.Interaction):
        """Display all unpaid wagers (admin view)."""
        await interaction.response.defer()
        
        unpaid = self.get_unpaid_wagers()
        
        if not unpaid:
            await interaction.followup.send("✅ No unpaid wagers! Everyone is paid up!")
            return
        
        embed = discord.Embed(
            title="💸 All Unpaid Wagers",
            description=f"**{len(unpaid)}** unpaid wager(s) in the league",
            color=discord.Color.red()
        )
        
        # Group by loser
        by_loser = {}
        for wager in unpaid:
            loser_id = self.get_loser_id(wager)
            if loser_id:
                if loser_id not in by_loser:
                    by_loser[loser_id] = {'wagers': [], 'total': 0}
                by_loser[loser_id]['wagers'].append(wager)
                by_loser[loser_id]['total'] += wager[7]  # amount
        
        for loser_id, data in list(by_loser.items())[:10]:
            try:
                loser = await self.bot.fetch_user(loser_id)
                loser_name = loser.display_name if loser else f"User {loser_id}"
            except:
                loser_name = f"User {loser_id}"
            
            embed.add_field(
                name=f"{loser_name}",
                value=f"**{len(data['wagers'])}** wager(s) | **${data['total']:.2f}** owed",
                inline=True
            )
        
        if len(by_loser) > 10:
            embed.add_field(
                name="...",
                value=f"And {len(by_loser) - 10} more members",
                inline=False
            )
        
        total_all = sum(d['total'] for d in by_loser.values())
        embed.set_footer(text=f"Total outstanding: ${total_all:.2f}")
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(PaymentRemindersCog(bot))
