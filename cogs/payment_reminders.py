"""
Payment Reminders Cog - Automatic reminders for unpaid wagers
Sends reminders every 2 days to users who owe money from settled wagers.
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
        self.reminder_channel_id = None  # Will be set to a specific channel
        self._ensure_reminder_table()
        
    def _ensure_reminder_table(self):
        """Ensure the reminder tracking table exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table to track when reminders were last sent
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wager_reminders (
                wager_id INTEGER PRIMARY KEY,
                last_reminder_sent TEXT,
                reminder_count INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    async def cog_load(self):
        """Called when the cog is loaded."""
        self.check_unpaid_wagers.start()
        logger.info("Payment reminders task started")
    
    async def cog_unload(self):
        """Called when the cog is unloaded."""
        self.check_unpaid_wagers.cancel()
        logger.info("Payment reminders task stopped")
    
    def get_unpaid_wagers(self):
        """Get all settled but unpaid wagers with loser information."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all settled wagers that haven't been paid
        # A wager is settled when winner_user_id is set, unpaid when is_paid = 0 or NULL
        cursor.execute('''
            SELECT w.wager_id, w.season_year, w.week, w.home_team_id, w.away_team_id,
                   w.home_user_id, w.away_user_id, w.amount, w.winner_user_id,
                   w.challenger_pick, w.opponent_pick, w.created_at,
                   r.last_reminder_sent, r.reminder_count
            FROM wagers w
            LEFT JOIN wager_reminders r ON w.wager_id = r.wager_id
            WHERE w.winner_user_id IS NOT NULL 
              AND (w.is_paid = 0 OR w.is_paid IS NULL)
            ORDER BY w.created_at ASC
        ''')
        
        wagers = cursor.fetchall()
        conn.close()
        return wagers
    
    def should_send_reminder(self, last_reminder_sent: Optional[str]) -> bool:
        """Check if 2 days have passed since the last reminder."""
        if last_reminder_sent is None:
            return True
        
        try:
            last_sent = datetime.fromisoformat(last_reminder_sent)
            time_since = datetime.now() - last_sent
            return time_since >= timedelta(days=2)
        except:
            return True
    
    def update_reminder_sent(self, wager_id: int):
        """Update the last reminder sent time for a wager."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO wager_reminders (wager_id, last_reminder_sent, reminder_count)
            VALUES (?, ?, 1)
            ON CONFLICT(wager_id) DO UPDATE SET
                last_reminder_sent = excluded.last_reminder_sent,
                reminder_count = wager_reminders.reminder_count + 1
        ''', (wager_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_loser_id(self, wager) -> Optional[int]:
        """Determine who lost the wager (the person who owes money)."""
        wager_id, season_year, week, home_team, away_team, home_user_id, away_user_id, amount, winner_user_id, challenger_pick, opponent_pick, created_at, last_reminder, reminder_count = wager
        
        if winner_user_id == home_user_id:
            return away_user_id
        elif winner_user_id == away_user_id:
            return home_user_id
        else:
            return None
    
    @tasks.loop(hours=12)  # Check twice a day
    async def check_unpaid_wagers(self):
        """Check for unpaid wagers and send reminders every 2 days."""
        await self.bot.wait_until_ready()
        
        logger.info("Checking for unpaid wagers to send reminders...")
        
        unpaid_wagers = self.get_unpaid_wagers()
        
        if not unpaid_wagers:
            logger.info("No unpaid wagers found")
            return
        
        # Group wagers by loser (person who owes)
        reminders_to_send = {}  # loser_id -> list of wager details
        
        for wager in unpaid_wagers:
            wager_id, season_year, week, home_team, away_team, home_user_id, away_user_id, amount, winner_user_id, challenger_pick, opponent_pick, created_at, last_reminder, reminder_count = wager
            
            # Check if we should send a reminder (2 days since last one)
            if not self.should_send_reminder(last_reminder):
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
                'reminder_count': reminder_count or 0
            })
        
        # Send reminders
        for loser_id, wagers in reminders_to_send.items():
            await self.send_reminder(loser_id, wagers)
    
    async def send_reminder(self, loser_id: int, wagers: list):
        """Send a reminder DM and channel message to the user who owes money."""
        try:
            user = await self.bot.fetch_user(loser_id)
            if user is None:
                logger.warning(f"Could not find user {loser_id}")
                return
            
            # Calculate total owed
            total_owed = sum(w['amount'] for w in wagers)
            
            # Build the reminder message
            embed = discord.Embed(
                title="💰 Wager Payment Reminder",
                description=f"Hey {user.mention}! You have **{len(wagers)}** unpaid wager(s) totaling **${total_owed:.2f}**.",
                color=discord.Color.orange()
            )
            
            # Add details for each unpaid wager
            for w in wagers[:10]:  # Limit to 10 to avoid embed limits
                winner = await self.bot.fetch_user(w['winner_id'])
                winner_name = winner.display_name if winner else "Unknown"
                home_name = TEAM_NAMES.get(w['home_team'], w['home_team'])
                away_name = TEAM_NAMES.get(w['away_team'], w['away_team'])
                
                reminder_num = w['reminder_count'] + 1
                embed.add_field(
                    name=f"Wager #{w['wager_id']} - Week {w['week']}",
                    value=f"**{away_name} @ {home_name}**\nAmount: **${w['amount']:.2f}**\nOwed to: **{winner_name}**\n*Reminder #{reminder_num}*",
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
                value="After paying, tell the winner to use `/paid` or `/paid @you` to confirm receipt.\nUse `/mywagers` to see all your wagers.",
                inline=False
            )
            
            embed.set_footer(text="Reminders are sent every 2 days until payment is confirmed.")
            embed.timestamp = datetime.now()
            
            # Try to send DM first
            try:
                await user.send(embed=embed)
                logger.info(f"Sent DM reminder to {user.display_name} for {len(wagers)} unpaid wagers")
            except discord.Forbidden:
                logger.warning(f"Could not DM user {user.display_name}, will post in channel")
            
            # Post in #wagers channel (primary) or fallback channels
            for guild in self.bot.guilds:
                # Prioritize #wagers channel for logging
                channel = None
                for ch in guild.text_channels:
                    if ch.name.lower() in ['wagers', 'wager-log', 'wager-logs']:
                        channel = ch
                        break
                
                if channel is None:
                    channel = discord.utils.get(guild.text_channels, name='bot-commands')
                if channel is None:
                    channel = discord.utils.get(guild.text_channels, name='general')
                
                if channel:
                    # Create a detailed public reminder for the wagers channel
                    public_embed = discord.Embed(
                        title="⏰ Payment Reminder",
                        description=f"{user.mention} owes **${total_owed:.2f}** from **{len(wagers)}** unpaid wager(s)",
                        color=discord.Color.red()
                    )
                    
                    # Add wager details
                    for w in wagers[:5]:  # Show up to 5 wagers
                        winner = await self.bot.fetch_user(w['winner_id'])
                        winner_name = winner.display_name if winner else "Unknown"
                        home_name = TEAM_NAMES.get(w['home_team'], w['home_team'])
                        away_name = TEAM_NAMES.get(w['away_team'], w['away_team'])
                        public_embed.add_field(
                            name=f"${w['amount']:.2f} to {winner_name}",
                            value=f"{away_name} @ {home_name} (Wk {w['week']})",
                            inline=True
                        )
                    
                    if len(wagers) > 5:
                        public_embed.add_field(
                            name="...",
                            value=f"And {len(wagers) - 5} more",
                            inline=True
                        )
                    
                    public_embed.set_footer(text="Reminder #{} | Use /paid to confirm payments".format(wagers[0]['reminder_count'] + 1))
                    public_embed.timestamp = datetime.now()
                    
                    try:
                        await channel.send(embed=public_embed)
                        logger.info(f"Posted public reminder for {user.display_name} in {channel.name}")
                    except discord.Forbidden:
                        logger.warning(f"Could not post in channel {channel.name}")
                    break
            
            # Update reminder tracking for each wager
            for w in wagers:
                self.update_reminder_sent(w['wager_id'])
                
        except Exception as e:
            logger.error(f"Error sending reminder to user {loser_id}: {e}")
    
    @check_unpaid_wagers.before_loop
    async def before_check_unpaid_wagers(self):
        """Wait for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()
        logger.info("Payment reminders task is ready")
    
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
            f"Running reminder check now...",
            ephemeral=True
        )
        
        # Trigger the check
        await self.check_unpaid_wagers()
        
        await interaction.followup.send("✅ Reminder check complete! Reminders sent where applicable.", ephemeral=True)
    
    @app_commands.command(name="allunpaidwagers", description="Show all unpaid wagers in the league (admin view)")
    @app_commands.default_permissions(administrator=True)
    async def all_unpaid_wagers(self, interaction: discord.Interaction):
        """Display all unpaid wagers (admin view)."""
        await interaction.response.defer()
        
        unpaid = self.get_unpaid_wagers()
        
        if not unpaid:
            await interaction.followup.send("✅ No unpaid wagers! Everyone is paid up!")
            return
        
        embed = discord.Embed(
            title="💸 Unpaid Wagers",
            description=f"There are **{len(unpaid)}** unpaid wagers in the league.",
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
        
        # Add fields for each debtor
        for loser_id, data in list(by_loser.items())[:10]:  # Limit to 10
            try:
                user = await self.bot.fetch_user(loser_id)
                user_name = user.display_name if user else f"User {loser_id}"
            except:
                user_name = f"User {loser_id}"
            
            wager_list = []
            for w in data['wagers'][:3]:  # Show up to 3 wagers per person
                wager_list.append(f"• Wager #{w[0]}: ${w[7]:.2f}")
            
            if len(data['wagers']) > 3:
                wager_list.append(f"• ...and {len(data['wagers']) - 3} more")
            
            embed.add_field(
                name=f"💰 {user_name}",
                value=f"**Owes: ${data['total']:.2f}**\n" + "\n".join(wager_list),
                inline=True
            )
        
        if len(by_loser) > 10:
            embed.add_field(
                name="...",
                value=f"And {len(by_loser) - 10} more users with unpaid wagers",
                inline=False
            )
        
        embed.set_footer(text="Reminders are automatically sent every 2 days")
        embed.timestamp = datetime.now()
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(PaymentRemindersCog(bot))
