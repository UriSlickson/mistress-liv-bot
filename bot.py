#!/usr/bin/env python3
"""
Mistress LIV Discord Bot
A comprehensive bot for managing a Madden fantasy league with payment tracking,
wager system, franchise statistics, and Reddit recruitment automation.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import logging
import re
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('MistressLIV')

# NFL Team data with custom helmet emojis (uploaded to server)
NFL_TEAMS = {
    # AFC East
    'BUF': {'name': 'Bills', 'conference': 'AFC', 'division': 'East', 'emoji': '<:bufhelmet:1458225301019427121>', 'color': 0x00338D},
    'MIA': {'name': 'Dolphins', 'conference': 'AFC', 'division': 'East', 'emoji': '<:miahelmet:1458225429684162712>', 'color': 0x008E97},
    'NE': {'name': 'Patriots', 'conference': 'AFC', 'division': 'East', 'emoji': '<:nehelmet:1458225445249093805>', 'color': 0x002244},
    'NYJ': {'name': 'Jets', 'conference': 'AFC', 'division': 'East', 'emoji': '<:nyjhelmet:1458225468917547170>', 'color': 0x125740},
    # AFC North
    'BAL': {'name': 'Ravens', 'conference': 'AFC', 'division': 'North', 'emoji': '<:balhelmet:1458225293029413029>', 'color': 0x241773},
    'CIN': {'name': 'Bengals', 'conference': 'AFC', 'division': 'North', 'emoji': '<:cinhelmet:1458225325136679187>', 'color': 0xFB4F14},
    'CLE': {'name': 'Browns', 'conference': 'AFC', 'division': 'North', 'emoji': '<:clehelmet:1458225333521223750>', 'color': 0x311D00},
    'PIT': {'name': 'Steelers', 'conference': 'AFC', 'division': 'North', 'emoji': '<:pithelmet:1458225488915988573>', 'color': 0xFFB612},
    # AFC South
    'HOU': {'name': 'Texans', 'conference': 'AFC', 'division': 'South', 'emoji': '<:houhelmet:1458225372708737164>', 'color': 0x03202F},
    'IND': {'name': 'Colts', 'conference': 'AFC', 'division': 'South', 'emoji': '<:indhelmet:1458225379473887405>', 'color': 0x002C5F},
    'JAX': {'name': 'Jaguars', 'conference': 'AFC', 'division': 'South', 'emoji': '<:jaxhelmet:1458225387799843010>', 'color': 0x006778},
    'TEN': {'name': 'Titans', 'conference': 'AFC', 'division': 'South', 'emoji': '<:tenhelmet:1458225521576906794>', 'color': 0x0C2340},
    # AFC West
    'DEN': {'name': 'Broncos', 'conference': 'AFC', 'division': 'West', 'emoji': '<:denhelmet:1458225349321298123>', 'color': 0xFB4F14},
    'KC': {'name': 'Chiefs', 'conference': 'AFC', 'division': 'West', 'emoji': '<:kchelmet:1458225396410482769>', 'color': 0xE31837},
    'LV': {'name': 'Raiders', 'conference': 'AFC', 'division': 'West', 'emoji': '<:lvhelmet:1458225420989108297>', 'color': 0x000000},
    'LAC': {'name': 'Chargers', 'conference': 'AFC', 'division': 'West', 'emoji': '<:lachelmet:1458225404589375548>', 'color': 0x0080C6},
    # NFC East
    'DAL': {'name': 'Cowboys', 'conference': 'NFC', 'division': 'East', 'emoji': '<:dalhelmet:1458225342287184059>', 'color': 0x003594},
    'NYG': {'name': 'Giants', 'conference': 'NFC', 'division': 'East', 'emoji': '<:nyghelmet:1458225461686571192>', 'color': 0x0B2265},
    'PHI': {'name': 'Eagles', 'conference': 'NFC', 'division': 'East', 'emoji': '<:phihelmet:1458225476219965492>', 'color': 0x004C54},
    'WAS': {'name': 'Commanders', 'conference': 'NFC', 'division': 'East', 'emoji': '<:washelmet:1458225528879186097>', 'color': 0x5A1414},
    # NFC North
    'CHI': {'name': 'Bears', 'conference': 'NFC', 'division': 'North', 'emoji': '<:chihelmet:1458225317071028390>', 'color': 0x0B162A},
    'DET': {'name': 'Lions', 'conference': 'NFC', 'division': 'North', 'emoji': '<:dethelmet:1458225356556337245>', 'color': 0x0076B6},
    'GB': {'name': 'Packers', 'conference': 'NFC', 'division': 'North', 'emoji': '<:gbhelmet:1458225365217579190>', 'color': 0x203731},
    'MIN': {'name': 'Vikings', 'conference': 'NFC', 'division': 'North', 'emoji': '<:minhelmet:1458225438173167636>', 'color': 0x4F2683},
    # NFC South
    'ATL': {'name': 'Falcons', 'conference': 'NFC', 'division': 'South', 'emoji': '<:atlhelmet:1458225284900851898>', 'color': 0xA71930},
    'CAR': {'name': 'Panthers', 'conference': 'NFC', 'division': 'South', 'emoji': '<:carhelmet:1458225309076684894>', 'color': 0x0085CA},
    'NO': {'name': 'Saints', 'conference': 'NFC', 'division': 'South', 'emoji': '<:nohelmet:1458225453503352855>', 'color': 0xD3BC8D},
    'TB': {'name': 'Buccaneers', 'conference': 'NFC', 'division': 'South', 'emoji': '<:tbhelmet:1458225513305997314>', 'color': 0xD50A0A},
    # NFC West
    'ARI': {'name': 'Cardinals', 'conference': 'NFC', 'division': 'West', 'emoji': '<:arihelmet:1458225274884849760>', 'color': 0x97233F},
    'LAR': {'name': 'Rams', 'conference': 'NFC', 'division': 'West', 'emoji': '<:larhelmet:1458225412961468446>', 'color': 0x003594},
    'SF': {'name': '49ers', 'conference': 'NFC', 'division': 'West', 'emoji': '<:sfhelmet:1458225505726632222>', 'color': 0xAA0000},
    'SEA': {'name': 'Seahawks', 'conference': 'NFC', 'division': 'West', 'emoji': '<:seahelmet:1458225497036165234>', 'color': 0x002244},
}

# Regex pattern to match custom Discord emojis in nicknames
HELMET_EMOJI_PATTERN = re.compile(r'^<:[a-z]+helmet:\d+>\s*')

# Bot configuration
class MistressLIVBot(commands.Bot):
    def __init__(self):
        # Set up intents - using default intents (Server Members Intent not available)
        intents = discord.Intents.default()
        intents.message_content = True  # For @mention responses
        # intents.members = True  # Disabled - using command interaction auto-registration instead
        intents.guilds = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            description='Mistress LIV Madden League Bot'
        )
        
        self.db_path = 'data/mistress_liv.db'
        self.guild_id = 1069671786276454492  # Mistress LIV server ID
        
    async def setup_hook(self):
        """Called when the bot is starting up."""
        # Initialize database
        self.init_database()
        
        # Load cogs
        await self.load_extension('cogs.payments')
        await self.load_extension('cogs.wagers')
        await self.load_extension('cogs.stats')
        await self.load_extension('cogs.recruitment')
        await self.load_extension('cogs.admin')
        await self.load_extension('cogs.conversations')
        await self.load_extension('cogs.profitability')
        await self.load_extension('cogs.announcements')
        await self.load_extension('cogs.registration')
        await self.load_extension('cogs.whiner')
        await self.load_extension('cogs.auto_settlement')
        await self.load_extension('cogs.command_guide')
        await self.load_extension('cogs.auto_seeding')
        await self.load_extension('cogs.payment_reminders')
        await self.load_extension('cogs.madden_export')
        await self.load_extension('cogs.snallabot_integration')
        
        # Sync slash commands
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} commands to guild {self.guild_id}")
        for cmd in synced:
            logger.info(f"  - /{cmd.name}")
        
        logger.info("Bot setup complete!")
        
    def init_database(self):
        """Initialize the SQLite database with required tables."""
        os.makedirs('data', exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER PRIMARY KEY,
                mymadden_username TEXT,
                venmo_handle TEXT,
                cashapp_handle TEXT,
                paypal_email TEXT,
                apple_pay_info TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Teams table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                team_id TEXT PRIMARY KEY,
                team_name TEXT NOT NULL,
                conference TEXT NOT NULL,
                division TEXT NOT NULL,
                user_discord_id INTEGER,
                is_cpu INTEGER DEFAULT 0,
                FOREIGN KEY (user_discord_id) REFERENCES users(discord_id)
            )
        ''')
        
        # Payments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_year INTEGER NOT NULL,
                payer_discord_id INTEGER NOT NULL,
                payee_discord_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                reason TEXT,
                due_date TEXT,
                is_paid INTEGER DEFAULT 0,
                paid_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (payer_discord_id) REFERENCES users(discord_id),
                FOREIGN KEY (payee_discord_id) REFERENCES users(discord_id)
            )
        ''')
        
        # Wagers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wagers (
                wager_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_year INTEGER NOT NULL,
                week INTEGER NOT NULL,
                week_type TEXT DEFAULT 'regular',
                home_team_id TEXT NOT NULL,
                away_team_id TEXT NOT NULL,
                home_user_id INTEGER,
                away_user_id INTEGER,
                amount REAL DEFAULT 0,
                home_accepted INTEGER DEFAULT 0,
                away_accepted INTEGER DEFAULT 0,
                winner_team_id TEXT,
                winner_user_id INTEGER,
                is_paid INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (home_user_id) REFERENCES users(discord_id),
                FOREIGN KEY (away_user_id) REFERENCES users(discord_id)
            )
        ''')
        
        # Franchise stats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS franchise_stats (
                user_discord_id INTEGER PRIMARY KEY,
                total_wins INTEGER DEFAULT 0,
                total_losses INTEGER DEFAULT 0,
                playoff_appearances INTEGER DEFAULT 0,
                division_titles INTEGER DEFAULT 0,
                conference_titles INTEGER DEFAULT 0,
                super_bowl_wins INTEGER DEFAULT 0,
                total_earnings REAL DEFAULT 0,
                total_wager_wins REAL DEFAULT 0,
                total_wager_losses REAL DEFAULT 0,
                FOREIGN KEY (user_discord_id) REFERENCES users(discord_id)
            )
        ''')
        
        # Season results table (for historical tracking)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS season_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_year INTEGER NOT NULL,
                user_discord_id INTEGER NOT NULL,
                team_id TEXT NOT NULL,
                conference TEXT NOT NULL,
                final_seed INTEGER,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                playoff_result TEXT,
                earnings REAL DEFAULT 0,
                FOREIGN KEY (user_discord_id) REFERENCES users(discord_id)
            )
        ''')
        
        # Populate teams table if empty
        cursor.execute('SELECT COUNT(*) FROM teams')
        if cursor.fetchone()[0] == 0:
            for team_id, team_data in NFL_TEAMS.items():
                cursor.execute('''
                    INSERT INTO teams (team_id, team_name, conference, division)
                    VALUES (?, ?, ?, ?)
                ''', (team_id, team_data['name'], team_data['conference'], team_data['division']))
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully!")
        
    async def on_ready(self):
        """Called when the bot is fully connected and ready."""
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} guild(s)')
        
        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="Mistress LIV | /help"
        )
        await self.change_presence(activity=activity)
        
        # Note: Auto-registration happens via command interactions (on_app_command_completion)
        # since Server Members Intent is not available
        logger.info("Auto-registration will occur when users interact with bot commands")
    
    # NOTE: auto_register_and_sync removed - requires Server Members Intent
    # Registration now happens via:
    # 1. /register command (user self-registers)
    # 2. /registeruser @user (admin registers user)
    # 3. /bulkregister (admin registers multiple users via mentions)
    # 4. on_member_update listener (auto-registers when role is assigned)
    
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        """Called after any slash command completes - auto-register user if they have a team role."""
        member = interaction.user
        if member.bot:
            return
        
        # Find their team role
        team_role = None
        for role in member.roles:
            role_name_upper = role.name.upper()
            if role_name_upper in NFL_TEAMS:
                team_role = role_name_upper
                break
        
        if team_role:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                # Check if already registered
                cursor.execute("SELECT user_discord_id FROM teams WHERE team_id = ?", (team_role,))
                result = cursor.fetchone()
                if result and result[0] != member.id:
                    # Update registration
                    cursor.execute(
                        "UPDATE teams SET user_discord_id = ? WHERE team_id = ?",
                        (member.id, team_role)
                    )
                    conn.commit()
                    logger.info(f"Auto-registered {member.display_name} as {team_role} owner via command")
                elif not result or result[0] is None:
                    cursor.execute(
                        "UPDATE teams SET user_discord_id = ? WHERE team_id = ?",
                        (member.id, team_role)
                    )
                    conn.commit()
                    logger.info(f"Auto-registered {member.display_name} as {team_role} owner via command")
                conn.close()
            except Exception as e:
                logger.error(f"Error auto-registering via command: {e}")
    
    async def on_member_update(self, before, after):
        """Called when a member's roles change - update helmet display and registration."""
        if before.roles != after.roles:
            # Check if a team role was added or removed
            await self.update_member_helmet(after)
            # Auto-register if team role was added
            await self.auto_register_member(after)
            
    async def update_member_helmet(self, member):
        """Update member's nickname to include/remove team helmet emoji based on role."""
        # Get the member's team role
        team_role = None
        for role in member.roles:
            role_name_upper = role.name.upper()
            if role_name_upper in NFL_TEAMS:
                team_role = role_name_upper
                break
        
        # Get current display name and remove any existing helmet emoji
        current_name = member.display_name
        base_name = self.remove_helmet_from_name(current_name)
        
        if team_role:
            # Member has a team role - add helmet emoji
            team_data = NFL_TEAMS[team_role]
            emoji = team_data['emoji']
            new_nickname = f"{emoji} {base_name}"
        else:
            # Member has no team role - remove helmet emoji (use base name)
            new_nickname = base_name
        
        # Only update if nickname actually changed
        if new_nickname != member.display_name:
            try:
                if len(new_nickname) <= 32:  # Discord nickname limit
                    await member.edit(nick=new_nickname if new_nickname != member.name else None)
                    logger.info(f"Updated nickname for {member.name} to '{new_nickname}'")
                else:
                    # Truncate if too long
                    truncated = new_nickname[:32]
                    await member.edit(nick=truncated)
                    logger.info(f"Updated nickname for {member.name} to '{truncated}' (truncated)")
            except discord.Forbidden:
                logger.warning(f"Cannot change nickname for {member.name} - insufficient permissions")
            except Exception as e:
                logger.error(f"Error updating nickname: {e}")
    
    async def auto_register_member(self, member):
        """Auto-register a member if they have a team role."""
        if member.bot:
            return
        
        # Find their team role
        team_role = None
        for role in member.roles:
            role_name_upper = role.name.upper()
            if role_name_upper in NFL_TEAMS:
                team_role = role_name_upper
                break
        
        if team_role:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE teams SET user_discord_id = ? WHERE team_id = ?",
                    (member.id, team_role)
                )
                conn.commit()
                conn.close()
                logger.info(f"Auto-registered {member.display_name} as {team_role} owner (role update)")
            except Exception as e:
                logger.error(f"Error auto-registering member: {e}")
    
    async def on_message(self, message):
        """Handle text commands like !commands."""
        # Ignore messages from bots
        if message.author.bot:
            return
        
        # Check for !commands
        if message.content.lower().strip() == '!commands':
            embed = discord.Embed(
                title="\ud83d\udccb MISTRESS LIV LEAGUE COMMANDS",
                color=discord.Color.gold()
            )
            
            # MyMadden Commands
            mymadden = (
                "`/register` - Register for the league\n"
                "`/connectservices` - Link your game accounts\n"
                "`/players` - View player database\n"
                "`/sync info` - Sync league info\n"
                "`/sync stats` - Sync player stats\n"
                "`/sync rosters` - Sync team rosters\n"
                "`/standings` - View league standings\n"
                "`/schedule` - View game schedule"
            )
            embed.add_field(name="\ud83c\udfc8 MyMadden", value=mymadden, inline=False)
            
            # Registration Commands
            reg_cmds = (
                "`/register` - Register as team owner\n"
                "`/unregister` - Unregister from announcements\n"
                "`/whoregistered` - See all registered owners"
            )
            embed.add_field(name="\ud83d\udcdd Registration", value=reg_cmds, inline=True)
            
            # Info Commands
            info_cmds = "`/help` - View all commands\n`/serverinfo` - Server details\n`/ping` - Check bot latency"
            embed.add_field(name="\u2139\ufe0f Info", value=info_cmds, inline=True)
            
            # Payment Commands
            payment_cmds = (
                "`/mypayments` - Your payment summary\n"
                "`/whooowesme` - Who owes YOU money\n"
                "`/whoiowe` - Who YOU owe money to\n"
                "`/paymentschedule` - All outstanding payments\n"
                "`/markpaid` - Mark a debt as paid\n"
                "`/topearners` - Earnings leaderboard\n"
                "`/toplosers` - Losses leaderboard"
            )
            embed.add_field(name="\ud83d\udcb0 Payments & Dues", value=payment_cmds, inline=False)
            
            # Wager Commands
            wager_cmds = (
                "`/wager` - Create a wager with opponent\n"
                "`/mywagers` - View your active wagers\n"
                "`/wagerboard` - Wager leaderboard\n"
                "`/markwagerpaid` - Mark wager as paid\n"
                "`/pendingwagers` - View unsettled wagers\n"
                "`/checkscore` - Check game result from MyMadden"
            )
            embed.add_field(name="\ud83c\udfb0 Wagers", value=wager_cmds, inline=True)
            
            # Profitability Commands
            profit_cmds = (
                "`/profitability` - League standings\n"
                "`/myprofit` - Your profit breakdown\n"
                "`/viewpairings` - AFC/NFC seed pairings\n"
                "`/payoutstructure` - View payout rules"
            )
            embed.add_field(name="\ud83d\udcca Profitability", value=profit_cmds, inline=True)
            
            # Fun Commands
            fun_cmds = "`/whiner` - Who complains most\n`/mywhines` - Your complaint stats"
            embed.add_field(name="\ud83d\ude24 Fun", value=fun_cmds, inline=True)
            
            # Admin Commands
            admin_cmds = (
                "`/announce` - Post announcement\n"
                "`/dmowners` - DM all team owners\n"
                "`/createpayment` - Create payment\n"
                "`/clearpayment` - Clear a payment\n"
                "`/generatepayments` - Generate dues\n"
                "`/setseeding` - Set playoff seeding\n"
                "`/setplayoffwinner` - Record playoff win\n"
                "`/clearplayoffresults` - Clear playoff data\n"
                "`/resetwhiner` - Reset whiner stats\n"
                "`/registerall` - Register all owners\n"
                "`/setuproles` - Create team roles\n"
                "`/settlewager` - Manually settle wager\n"
                "`/parsescore` - Test score parsing\n"
                "`/forcecheckwagers` - Force check all wagers\n"
                "`/checkscore` - Check game from website"
            )
            embed.add_field(name="\ud83d\udd27 Admin Only", value=admin_cmds, inline=False)
            
            embed.set_footer(text="Use / to access slash commands | !commands to show this list")
            
            await message.channel.send(embed=embed)
            return
        
        # Process other commands (if any)
        await self.process_commands(message)

    def remove_helmet_from_name(self, name):
        """Remove any helmet emoji prefix from a name."""
        # Remove custom emoji pattern (e.g., <:bufhelmet:123456789>)
        name = HELMET_EMOJI_PATTERN.sub('', name)
        
        # Also remove any legacy Unicode emoji prefixes (for backwards compatibility)
        legacy_emojis = ['🦬', '🐬', '🏈', '✈️', '🐦‍⬛', '🐅', '🟤', '⚙️', '🤠', '🐴', '🐆', '⚔️',
                        '🐎', '🪶', '☠️', '⚡', '⭐', '🗽', '🦅', '🎖️', '🐻', '🦁', '🧀', '⚜️',
                        '🏴‍☠️', '🐦', '🐏', '⛏️']
        for emoji in legacy_emojis:
            if name.startswith(emoji + ' '):
                name = name[len(emoji) + 1:]
                break
            elif name.startswith(emoji):
                name = name[len(emoji):]
                break
        
        return name.strip()


def main():
    """Main entry point for the bot."""
    # Get token from environment variable
    token = os.getenv('DISCORD_TOKEN')
    
    if not token:
        logger.error("DISCORD_BOT_TOKEN environment variable not set!")
        logger.info("Please set the token: export DISCORD_BOT_TOKEN='your_token_here'")
        return
    
    bot = MistressLIVBot()
    bot.run(token)


if __name__ == '__main__':
    main()
