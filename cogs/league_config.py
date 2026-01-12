"""
League Configuration Cog
Manages guild-specific league settings for multi-server/multi-league support.

Features:
- Per-guild league configuration
- Multiple platform support (PS5, Xbox, PC, Amazon Luna)
- Setup wizard for new servers
- League switching for servers with multiple leagues
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List

logger = logging.getLogger('MistressLIV.LeagueConfig')

# Supported platforms
PLATFORMS = {
    'ps5': 'PlayStation 5',
    'ps4': 'PlayStation 4',
    'xbox': 'Xbox Series X|S',
    'xboxone': 'Xbox One',
    'pc': 'PC',
    'luna': 'Amazon Luna'
}

# Platform choices for commands
PLATFORM_CHOICES = [
    app_commands.Choice(name="PlayStation 5", value="ps5"),
    app_commands.Choice(name="PlayStation 4", value="ps4"),
    app_commands.Choice(name="Xbox Series X|S", value="xbox"),
    app_commands.Choice(name="Xbox One", value="xboxone"),
    app_commands.Choice(name="PC", value="pc"),
    app_commands.Choice(name="Amazon Luna", value="luna"),
]


class LeagueConfigCog(commands.Cog):
    """Cog for managing league configurations per guild."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
        self._config_cache = {}  # Cache configs to reduce DB calls
        
    def get_db_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def _ensure_tables(self):
        """Create required tables for league configuration."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Guild configuration table - stores active league per guild
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                active_league_id INTEGER,
                setup_complete INTEGER DEFAULT 0,
                welcome_channel_id INTEGER,
                wagers_channel_id INTEGER,
                payouts_channel_id INTEGER,
                bestball_channel_id INTEGER,
                scores_channel_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Leagues table - stores all leagues (can have multiple per guild)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leagues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                league_name TEXT NOT NULL,
                league_id TEXT NOT NULL,
                platform TEXT DEFAULT 'ps5',
                mymadden_url TEXT,
                snallabot_enabled INTEGER DEFAULT 1,
                is_active INTEGER DEFAULT 1,
                current_season INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, league_id)
            )
        ''')
        
        # Migrate existing snallabot_config data if it exists
        cursor.execute('''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='snallabot_config'
        ''')
        if cursor.fetchone():
            cursor.execute('''
                SELECT guild_id, league_id, platform, current_season 
                FROM snallabot_config
            ''')
            existing = cursor.fetchall()
            for guild_id, league_id, platform, season in existing:
                cursor.execute('''
                    INSERT OR IGNORE INTO leagues 
                    (guild_id, league_name, league_id, platform, current_season)
                    VALUES (?, ?, ?, ?, ?)
                ''', (guild_id, 'Default League', league_id or 'liv', platform or 'ps5', season))
                
                # Set as active league
                cursor.execute('''
                    INSERT OR IGNORE INTO guild_config (guild_id, active_league_id, setup_complete)
                    SELECT ?, id, 1 FROM leagues WHERE guild_id = ? AND league_id = ?
                ''', (guild_id, guild_id, league_id or 'liv'))
        
        conn.commit()
        conn.close()
        logger.info("League configuration tables initialized")
    
    def get_guild_config(self, guild_id: int) -> Optional[dict]:
        """Get the configuration for a guild."""
        # Check cache first
        if guild_id in self._config_cache:
            return self._config_cache[guild_id]
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT gc.guild_id, gc.active_league_id, gc.setup_complete,
                   gc.wagers_channel_id, gc.payouts_channel_id, gc.bestball_channel_id,
                   gc.scores_channel_id,
                   l.league_name, l.league_id, l.platform, l.mymadden_url,
                   l.snallabot_enabled, l.current_season
            FROM guild_config gc
            LEFT JOIN leagues l ON gc.active_league_id = l.id
            WHERE gc.guild_id = ?
        ''', (guild_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            config = {
                'guild_id': result[0],
                'active_league_db_id': result[1],
                'setup_complete': bool(result[2]),
                'wagers_channel_id': result[3],
                'payouts_channel_id': result[4],
                'bestball_channel_id': result[5],
                'scores_channel_id': result[6],
                'league_name': result[7],
                'league_id': result[8],
                'platform': result[9],
                'mymadden_url': result[10],
                'snallabot_enabled': bool(result[11]) if result[11] is not None else True,
                'current_season': result[12]
            }
            self._config_cache[guild_id] = config
            return config
        
        return None
    
    def get_league_config(self, guild_id: int) -> Optional[dict]:
        """Get the active league configuration for a guild. Alias for get_guild_config."""
        config = self.get_guild_config(guild_id)
        if config and config.get('league_id'):
            return {
                'league_id': config['league_id'],
                'platform': config['platform'],
                'current_season': config['current_season'],
                'mymadden_url': config['mymadden_url'],
                'snallabot_enabled': config['snallabot_enabled']
            }
        return None
    
    def clear_cache(self, guild_id: int = None):
        """Clear the configuration cache."""
        if guild_id:
            self._config_cache.pop(guild_id, None)
        else:
            self._config_cache.clear()
    
    async def league_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for league selection."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, league_name, league_id, platform
            FROM leagues
            WHERE guild_id = ?
            ORDER BY league_name
        ''', (interaction.guild_id,))
        
        leagues = cursor.fetchall()
        conn.close()
        
        choices = []
        for db_id, name, league_id, platform in leagues:
            label = f"{name} ({league_id} - {PLATFORMS.get(platform, platform)})"
            if current and current.lower() not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label[:100], value=str(db_id)))
        
        return choices[:25]
    
    # ==================== COMMANDS ====================
    
    @app_commands.command(name="setupleague", description="Set up or update your league configuration")
    @app_commands.describe(
        league_name="Display name for your league (e.g., 'Mistress LIV')",
        league_id="Your MyMadden/Snallabot league ID (e.g., 'liv')",
        platform="Platform the league was created on"
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def setup_league(
        self,
        interaction: discord.Interaction,
        league_name: str,
        league_id: str,
        platform: app_commands.Choice[str]
    ):
        """Set up or update the league configuration for this server."""
        await interaction.response.defer()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if league already exists for this guild
        cursor.execute('''
            SELECT id FROM leagues WHERE guild_id = ? AND league_id = ?
        ''', (interaction.guild_id, league_id.lower()))
        existing = cursor.fetchone()
        
        mymadden_url = f"https://mymadden.com/lg/{league_id.lower()}"
        
        if existing:
            # Update existing league
            cursor.execute('''
                UPDATE leagues 
                SET league_name = ?, platform = ?, mymadden_url = ?, updated_at = ?
                WHERE id = ?
            ''', (league_name, platform.value, mymadden_url, datetime.now().isoformat(), existing[0]))
            league_db_id = existing[0]
            action = "updated"
        else:
            # Create new league
            cursor.execute('''
                INSERT INTO leagues (guild_id, league_name, league_id, platform, mymadden_url)
                VALUES (?, ?, ?, ?, ?)
            ''', (interaction.guild_id, league_name, league_id.lower(), platform.value, mymadden_url))
            league_db_id = cursor.lastrowid
            action = "created"
        
        # Set as active league for this guild
        cursor.execute('''
            INSERT INTO guild_config (guild_id, active_league_id, setup_complete)
            VALUES (?, ?, 1)
            ON CONFLICT(guild_id) DO UPDATE SET 
                active_league_id = ?, 
                setup_complete = 1,
                updated_at = ?
        ''', (interaction.guild_id, league_db_id, league_db_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        # Clear cache
        self.clear_cache(interaction.guild_id)
        
        embed = discord.Embed(
            title=f"✅ League {action.title()}!",
            description=f"**{league_name}** is now configured for this server.",
            color=discord.Color.green()
        )
        
        embed.add_field(name="📋 League ID", value=league_id.lower(), inline=True)
        embed.add_field(name="🎮 Platform", value=PLATFORMS.get(platform.value, platform.value), inline=True)
        embed.add_field(name="🔗 MyMadden", value=mymadden_url, inline=False)
        
        embed.add_field(
            name="📊 Snallabot API",
            value=f"`snallabot.me/{platform.value}/{league_id.lower()}/...`",
            inline=False
        )
        
        embed.set_footer(text="All bot features will now use this league configuration.")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="addleague", description="Add another league to this server")
    @app_commands.describe(
        league_name="Display name for the league",
        league_id="MyMadden/Snallabot league ID",
        platform="Platform the league was created on"
    )
    @app_commands.choices(platform=PLATFORM_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def add_league(
        self,
        interaction: discord.Interaction,
        league_name: str,
        league_id: str,
        platform: app_commands.Choice[str]
    ):
        """Add an additional league to this server (for servers managing multiple leagues)."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if league already exists
        cursor.execute('''
            SELECT id FROM leagues WHERE guild_id = ? AND league_id = ?
        ''', (interaction.guild_id, league_id.lower()))
        
        if cursor.fetchone():
            await interaction.response.send_message(
                f"❌ A league with ID `{league_id}` already exists in this server.",
                ephemeral=True
            )
            conn.close()
            return
        
        mymadden_url = f"https://mymadden.com/lg/{league_id.lower()}"
        
        cursor.execute('''
            INSERT INTO leagues (guild_id, league_name, league_id, platform, mymadden_url)
            VALUES (?, ?, ?, ?, ?)
        ''', (interaction.guild_id, league_name, league_id.lower(), platform.value, mymadden_url))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ League Added!",
            description=f"**{league_name}** has been added to this server.",
            color=discord.Color.green()
        )
        
        embed.add_field(name="📋 League ID", value=league_id.lower(), inline=True)
        embed.add_field(name="🎮 Platform", value=PLATFORMS.get(platform.value, platform.value), inline=True)
        embed.add_field(
            name="💡 Tip",
            value="Use `/switchleague` to change the active league for bot commands.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="switchleague", description="Switch the active league for this server")
    @app_commands.describe(league="Select the league to make active")
    @app_commands.default_permissions(administrator=True)
    async def switch_league(self, interaction: discord.Interaction, league: str):
        """Switch the active league for bot commands."""
        league_db_id = int(league)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Verify league belongs to this guild
        cursor.execute('''
            SELECT league_name, league_id, platform FROM leagues 
            WHERE id = ? AND guild_id = ?
        ''', (league_db_id, interaction.guild_id))
        
        result = cursor.fetchone()
        if not result:
            await interaction.response.send_message(
                "❌ League not found.",
                ephemeral=True
            )
            conn.close()
            return
        
        league_name, league_id, platform = result
        
        # Update active league
        cursor.execute('''
            UPDATE guild_config SET active_league_id = ?, updated_at = ?
            WHERE guild_id = ?
        ''', (league_db_id, datetime.now().isoformat(), interaction.guild_id))
        
        conn.commit()
        conn.close()
        
        # Clear cache
        self.clear_cache(interaction.guild_id)
        
        await interaction.response.send_message(
            f"✅ Switched active league to **{league_name}** (`{league_id}` on {PLATFORMS.get(platform, platform)})"
        )
    
    # Add autocomplete to switch_league
    @switch_league.autocomplete('league')
    async def switch_league_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        return await self.league_autocomplete(interaction, current)
    
    @app_commands.command(name="listleagues", description="List all leagues configured for this server")
    async def list_leagues(self, interaction: discord.Interaction):
        """Show all leagues configured for this server."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get active league ID
        cursor.execute('''
            SELECT active_league_id FROM guild_config WHERE guild_id = ?
        ''', (interaction.guild_id,))
        active_result = cursor.fetchone()
        active_id = active_result[0] if active_result else None
        
        # Get all leagues
        cursor.execute('''
            SELECT id, league_name, league_id, platform, current_season, mymadden_url
            FROM leagues
            WHERE guild_id = ?
            ORDER BY league_name
        ''', (interaction.guild_id,))
        
        leagues = cursor.fetchall()
        conn.close()
        
        if not leagues:
            await interaction.response.send_message(
                "❌ No leagues configured. Use `/setupleague` to add one!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🏈 Configured Leagues",
            description=f"This server has {len(leagues)} league(s) configured.",
            color=discord.Color.blue()
        )
        
        for db_id, name, league_id, platform, season, url in leagues:
            is_active = "✅ **ACTIVE**" if db_id == active_id else ""
            embed.add_field(
                name=f"{name} {is_active}",
                value=(
                    f"**ID:** `{league_id}`\n"
                    f"**Platform:** {PLATFORMS.get(platform, platform)}\n"
                    f"**Season:** {season or 'Not set'}\n"
                    f"**URL:** {url or 'N/A'}"
                ),
                inline=True
            )
        
        embed.set_footer(text="Use /switchleague to change the active league")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="leagueinfo", description="Show current league configuration")
    async def league_info(self, interaction: discord.Interaction):
        """Display the current active league configuration."""
        config = self.get_guild_config(interaction.guild_id)
        
        if not config or not config.get('league_id'):
            await interaction.response.send_message(
                "❌ No league configured. Use `/setupleague` to set one up!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🏈 {config['league_name'] or 'League Configuration'}",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="📋 League ID", value=config['league_id'], inline=True)
        embed.add_field(name="🎮 Platform", value=PLATFORMS.get(config['platform'], config['platform']), inline=True)
        embed.add_field(name="📅 Season", value=config['current_season'] or 'Not set', inline=True)
        
        if config['mymadden_url']:
            embed.add_field(name="🔗 MyMadden", value=config['mymadden_url'], inline=False)
        
        embed.add_field(
            name="📊 Snallabot API",
            value=f"{'✅ Enabled' if config['snallabot_enabled'] else '❌ Disabled'}",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="setseason", description="Set the current season for the active league")
    @app_commands.describe(season="The current Madden season year (e.g., 2026)")
    @app_commands.default_permissions(administrator=True)
    async def set_season(self, interaction: discord.Interaction, season: int):
        """Update the current season for the active league."""
        config = self.get_guild_config(interaction.guild_id)
        
        if not config or not config.get('active_league_db_id'):
            await interaction.response.send_message(
                "❌ No league configured. Use `/setupleague` first!",
                ephemeral=True
            )
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE leagues SET current_season = ?, updated_at = ?
            WHERE id = ?
        ''', (season, datetime.now().isoformat(), config['active_league_db_id']))
        
        conn.commit()
        conn.close()
        
        # Clear cache
        self.clear_cache(interaction.guild_id)
        
        await interaction.response.send_message(
            f"✅ Season updated to **{season}** for {config['league_name'] or 'active league'}."
        )
    
    @app_commands.command(name="removeleague", description="[Admin] Remove a league from this server")
    @app_commands.describe(league="Select the league to remove")
    @app_commands.default_permissions(administrator=True)
    async def remove_league(self, interaction: discord.Interaction, league: str):
        """Remove a league configuration from this server."""
        league_db_id = int(league)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if this is the active league
        cursor.execute('''
            SELECT active_league_id FROM guild_config WHERE guild_id = ?
        ''', (interaction.guild_id,))
        active_result = cursor.fetchone()
        
        if active_result and active_result[0] == league_db_id:
            await interaction.response.send_message(
                "❌ Cannot remove the active league. Switch to another league first with `/switchleague`.",
                ephemeral=True
            )
            conn.close()
            return
        
        # Get league name for confirmation
        cursor.execute('''
            SELECT league_name FROM leagues WHERE id = ? AND guild_id = ?
        ''', (league_db_id, interaction.guild_id))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                "❌ League not found.",
                ephemeral=True
            )
            conn.close()
            return
        
        league_name = result[0]
        
        # Delete the league
        cursor.execute('DELETE FROM leagues WHERE id = ?', (league_db_id,))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ League **{league_name}** has been removed from this server."
        )
    
    @remove_league.autocomplete('league')
    async def remove_league_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        return await self.league_autocomplete(interaction, current)
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Send setup wizard when bot joins a new server."""
        # Find a suitable channel to send the welcome message
        target_channel = None
        
        # Try to find a general or welcome channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                if 'general' in channel.name.lower() or 'welcome' in channel.name.lower():
                    target_channel = channel
                    break
        
        # Fallback to first channel with send permissions
        if not target_channel:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    break
        
        if not target_channel:
            logger.warning(f"Could not find a channel to send setup message in {guild.name}")
            return
        
        embed = discord.Embed(
            title="🏈 Welcome to Mistress LIV Bot!",
            description=(
                "Thanks for adding me to your server!\n\n"
                "I help manage Madden fantasy leagues with features like:\n"
                "• **Wagers** - Track bets between team owners\n"
                "• **Payments** - Manage dues and payouts\n"
                "• **Best Ball** - Fantasy football events\n"
                "• **Playoff Payouts** - Automated payment generation\n\n"
                "**Click the button below to set up your league!**"
            ),
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="🛠️ Quick Setup",
            value=(
                "You'll need:\n"
                "1. Your MyMadden league ID (e.g., `liv` from mymadden.com/lg/liv)\n"
                "2. The platform your league was created on"
            ),
            inline=False
        )
        
        embed.set_footer(text="Admins can also use /setupleague at any time")
        
        view = SetupWizardView(self)
        await target_channel.send(embed=embed, view=view)
        logger.info(f"Sent setup wizard to {guild.name}")

    @app_commands.command(name="setchannels", description="[Admin] Set channels for bot notifications")
    @app_commands.describe(
        wagers="Channel for wager notifications",
        payouts="Channel for payout notifications",
        bestball="Channel for Best Ball notifications",
        scores="Channel for game score notifications"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_channels(
        self,
        interaction: discord.Interaction,
        wagers: Optional[discord.TextChannel] = None,
        payouts: Optional[discord.TextChannel] = None,
        bestball: Optional[discord.TextChannel] = None,
        scores: Optional[discord.TextChannel] = None
    ):
        """Configure which channels the bot uses for notifications."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Ensure guild config exists
        cursor.execute('''
            INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)
        ''', (interaction.guild_id,))
        
        updates = []
        if wagers:
            cursor.execute('UPDATE guild_config SET wagers_channel_id = ? WHERE guild_id = ?',
                          (wagers.id, interaction.guild_id))
            updates.append(f"Wagers: {wagers.mention}")
        if payouts:
            cursor.execute('UPDATE guild_config SET payouts_channel_id = ? WHERE guild_id = ?',
                          (payouts.id, interaction.guild_id))
            updates.append(f"Payouts: {payouts.mention}")
        if bestball:
            cursor.execute('UPDATE guild_config SET bestball_channel_id = ? WHERE guild_id = ?',
                          (bestball.id, interaction.guild_id))
            updates.append(f"Best Ball: {bestball.mention}")
        if scores:
            cursor.execute('UPDATE guild_config SET scores_channel_id = ? WHERE guild_id = ?',
                          (scores.id, interaction.guild_id))
            updates.append(f"Scores: {scores.mention}")
        
        conn.commit()
        conn.close()
        
        # Clear cache
        self.clear_cache(interaction.guild_id)
        
        if updates:
            await interaction.response.send_message(
                f"✅ Channel settings updated:\n" + "\n".join(updates)
            )
        else:
            await interaction.response.send_message(
                "❌ No channels specified. Please select at least one channel to update.",
                ephemeral=True
            )


class SetupWizardView(discord.ui.View):
    """Interactive view for setting up a new server."""
    
    def __init__(self, cog):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.league_name = None
        self.league_id = None
        self.platform = None
        
    @discord.ui.button(label="Start Setup", style=discord.ButtonStyle.primary, emoji="🏈")
    async def start_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Start the setup wizard."""
        modal = SetupModal(self.cog)
        await interaction.response.send_modal(modal)
        self.stop()


class SetupModal(discord.ui.Modal, title="League Setup"):
    """Modal for entering league details."""
    
    league_name = discord.ui.TextInput(
        label="League Name",
        placeholder="e.g., Mistress LIV",
        required=True,
        max_length=100
    )
    
    league_id = discord.ui.TextInput(
        label="MyMadden League ID",
        placeholder="e.g., liv (from mymadden.com/lg/liv)",
        required=True,
        max_length=50
    )
    
    platform = discord.ui.TextInput(
        label="Platform (ps5, xbox, pc, luna)",
        placeholder="e.g., luna",
        required=True,
        max_length=20
    )
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        platform_value = self.platform.value.lower().strip()
        
        # Validate platform
        valid_platforms = ['ps5', 'ps4', 'xbox', 'xboxone', 'pc', 'luna']
        if platform_value not in valid_platforms:
            await interaction.response.send_message(
                f"❌ Invalid platform. Please use one of: {', '.join(valid_platforms)}",
                ephemeral=True
            )
            return
        
        conn = self.cog.get_db_connection()
        cursor = conn.cursor()
        
        league_id = self.league_id.value.lower().strip()
        mymadden_url = f"https://mymadden.com/lg/{league_id}"
        
        # Create league
        cursor.execute('''
            INSERT INTO leagues (guild_id, league_name, league_id, platform, mymadden_url)
            VALUES (?, ?, ?, ?, ?)
        ''', (interaction.guild_id, self.league_name.value, league_id, platform_value, mymadden_url))
        league_db_id = cursor.lastrowid
        
        # Set as active league
        cursor.execute('''
            INSERT INTO guild_config (guild_id, active_league_id, setup_complete)
            VALUES (?, ?, 1)
            ON CONFLICT(guild_id) DO UPDATE SET 
                active_league_id = ?, 
                setup_complete = 1,
                updated_at = ?
        ''', (interaction.guild_id, league_db_id, league_db_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        # Clear cache
        self.cog.clear_cache(interaction.guild_id)
        
        embed = discord.Embed(
            title="✅ Setup Complete!",
            description=f"**{self.league_name.value}** is now configured.",
            color=discord.Color.green()
        )
        
        embed.add_field(name="📋 League ID", value=league_id, inline=True)
        embed.add_field(name="🎮 Platform", value=PLATFORMS.get(platform_value, platform_value), inline=True)
        embed.add_field(name="🔗 MyMadden", value=mymadden_url, inline=False)
        
        embed.add_field(
            name="📚 Next Steps",
            value=(
                "• Use `/setchannels` to configure notification channels\n"
                "• Use `/setseason` to set the current season year\n"
                "• Use `/help` to see all available commands\n"
                "• Use `/postguide` to post the command guide"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)


# Helper function for other cogs to get league config
def get_league_config_for_guild(bot, guild_id: int) -> Optional[dict]:
    """
    Helper function for other cogs to get the league configuration.
    Returns dict with: league_id, platform, current_season, mymadden_url, snallabot_enabled
    """
    league_config_cog = bot.get_cog('LeagueConfigCog')
    if league_config_cog:
        return league_config_cog.get_league_config(guild_id)
    return None


async def setup(bot):
    await bot.add_cog(LeagueConfigCog(bot))
