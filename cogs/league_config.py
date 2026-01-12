"""
League Configuration Cog - Multi-guild league management
CONSOLIDATED COMMANDS:
/league setup - Set up or update league configuration
/league add - Add another league
/league switch - Switch active league
/league list - List all leagues
/league info - Show current league info
/league season - Set current season
/league remove - Remove a league (admin)
/league channels - Set notification channels (admin)
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from typing import Optional, List
import logging

logger = logging.getLogger('MistressLIV.LeagueConfig')

# Platform choices
PLATFORMS = [
    app_commands.Choice(name="PlayStation 5", value="ps5"),
    app_commands.Choice(name="PlayStation 4", value="ps4"),
    app_commands.Choice(name="Xbox Series X|S", value="xboxone"),
    app_commands.Choice(name="Xbox One", value="xboxone"),
    app_commands.Choice(name="PC", value="pc"),
    app_commands.Choice(name="Amazon Luna", value="xboxone"),
]


class LeagueConfigCog(commands.Cog):
    """Cog for multi-guild league configuration management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "data/mistress_liv.db"
        self._init_tables()
    
    def _init_tables(self):
        """Initialize league configuration tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Guild leagues table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_leagues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                league_name TEXT NOT NULL,
                league_id TEXT NOT NULL,
                platform TEXT DEFAULT 'xboxone',
                current_season INTEGER DEFAULT 2026,
                is_active INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, league_id)
            )
        ''')
        
        # Guild channels table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_channels (
                guild_id INTEGER PRIMARY KEY,
                wagers_channel_id INTEGER,
                payouts_channel_id INTEGER,
                scores_channel_id INTEGER,
                announcements_channel_id INTEGER,
                bestball_channel_id INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("League config tables initialized")
    
    def get_active_league(self, guild_id: int) -> Optional[dict]:
        """Get the active league for a guild."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT league_name, league_id, platform, current_season
            FROM guild_leagues WHERE guild_id = ? AND is_active = 1
        ''', (guild_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'league_name': row[0],
                'league_id': row[1],
                'platform': row[2],
                'current_season': row[3]
            }
        return None
    
    async def _league_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for league selection."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT league_name, league_id FROM guild_leagues
            WHERE guild_id = ?
        ''', (interaction.guild_id,))
        leagues = cursor.fetchall()
        conn.close()
        
        choices = []
        for name, league_id in leagues:
            if current.lower() in name.lower() or current.lower() in league_id.lower():
                choices.append(app_commands.Choice(name=f"{name} ({league_id})", value=league_id))
        return choices[:25]

    # ==================== LEAGUE COMMAND GROUP ====================
    
    league_group = app_commands.Group(name="league", description="League configuration commands")
    
    @league_group.command(name="setup", description="Set up or update your league configuration")
    @app_commands.describe(
        league_name="Display name for your league",
        league_id="MyMadden/Snallabot league ID (e.g., 'liv')",
        platform="Gaming platform"
    )
    @app_commands.choices(platform=PLATFORMS)
    @app_commands.checks.has_permissions(administrator=True)
    async def league_setup(
        self,
        interaction: discord.Interaction,
        league_name: str,
        league_id: str,
        platform: app_commands.Choice[str]
    ):
        """Set up the primary league for this server."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Deactivate any existing active league
        cursor.execute('UPDATE guild_leagues SET is_active = 0 WHERE guild_id = ?', (interaction.guild_id,))
        
        # Insert or update the league
        cursor.execute('''
            INSERT INTO guild_leagues (guild_id, league_name, league_id, platform, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(guild_id, league_id) DO UPDATE SET
                league_name = excluded.league_name,
                platform = excluded.platform,
                is_active = 1
        ''', (interaction.guild_id, league_name, league_id.lower(), platform.value))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ League Configured!",
            color=discord.Color.green()
        )
        embed.add_field(name="League Name", value=league_name, inline=True)
        embed.add_field(name="League ID", value=league_id.lower(), inline=True)
        embed.add_field(name="Platform", value=platform.name, inline=True)
        embed.add_field(
            name="MyMadden URL",
            value=f"https://mymadden.com/lg/{league_id.lower()}",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    @league_group.command(name="add", description="Add another league to this server")
    @app_commands.describe(
        league_name="Display name for the league",
        league_id="MyMadden/Snallabot league ID",
        platform="Gaming platform"
    )
    @app_commands.choices(platform=PLATFORMS)
    @app_commands.checks.has_permissions(administrator=True)
    async def league_add(
        self,
        interaction: discord.Interaction,
        league_name: str,
        league_id: str,
        platform: app_commands.Choice[str]
    ):
        """Add an additional league to this server."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO guild_leagues (guild_id, league_name, league_id, platform, is_active)
                VALUES (?, ?, ?, ?, 0)
            ''', (interaction.guild_id, league_name, league_id.lower(), platform.value))
            conn.commit()
            
            await interaction.response.send_message(
                f"✅ Added league **{league_name}** ({league_id}). Use `/league switch` to activate it."
            )
        except sqlite3.IntegrityError:
            await interaction.response.send_message(
                f"❌ League ID '{league_id}' already exists for this server.",
                ephemeral=True
            )
        finally:
            conn.close()
    
    @league_group.command(name="switch", description="Switch the active league")
    @app_commands.describe(league="Select the league to activate")
    @app_commands.autocomplete(league=_league_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def league_switch(self, interaction: discord.Interaction, league: str):
        """Switch to a different league."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Deactivate all
        cursor.execute('UPDATE guild_leagues SET is_active = 0 WHERE guild_id = ?', (interaction.guild_id,))
        
        # Activate selected
        cursor.execute('''
            UPDATE guild_leagues SET is_active = 1
            WHERE guild_id = ? AND league_id = ?
        ''', (interaction.guild_id, league))
        
        if cursor.rowcount > 0:
            cursor.execute('SELECT league_name FROM guild_leagues WHERE guild_id = ? AND league_id = ?',
                          (interaction.guild_id, league))
            name = cursor.fetchone()[0]
            conn.commit()
            await interaction.response.send_message(f"✅ Switched to **{name}** ({league})")
        else:
            await interaction.response.send_message(f"❌ League '{league}' not found.", ephemeral=True)
        
        conn.close()
    
    @league_group.command(name="list", description="List all leagues for this server")
    async def league_list(self, interaction: discord.Interaction):
        """List all configured leagues."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT league_name, league_id, platform, current_season, is_active
            FROM guild_leagues WHERE guild_id = ?
        ''', (interaction.guild_id,))
        leagues = cursor.fetchall()
        conn.close()
        
        if not leagues:
            await interaction.response.send_message(
                "No leagues configured. Use `/league setup` to add one!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🏈 Configured Leagues",
            color=discord.Color.blue()
        )
        
        for name, league_id, platform, season, is_active in leagues:
            status = "✅ Active" if is_active else "⚪ Inactive"
            embed.add_field(
                name=f"{name} ({league_id})",
                value=f"Platform: {platform}\nSeason: {season}\nStatus: {status}",
                inline=True
            )
        
        await interaction.response.send_message(embed=embed)
    
    @league_group.command(name="info", description="Show current league configuration")
    async def league_info(self, interaction: discord.Interaction):
        """Show current active league info."""
        league = self.get_active_league(interaction.guild_id)
        
        if not league:
            await interaction.response.send_message(
                "No active league. Use `/league setup` to configure one!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🏈 {league['league_name']}",
            color=discord.Color.blue()
        )
        embed.add_field(name="League ID", value=league['league_id'], inline=True)
        embed.add_field(name="Platform", value=league['platform'], inline=True)
        embed.add_field(name="Season", value=str(league['current_season']), inline=True)
        embed.add_field(
            name="MyMadden",
            value=f"https://mymadden.com/lg/{league['league_id']}",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @league_group.command(name="season", description="Set the current season")
    @app_commands.describe(year="Season year (e.g., 2026)")
    @app_commands.checks.has_permissions(administrator=True)
    async def league_season(self, interaction: discord.Interaction, year: int):
        """Set the current season year."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE guild_leagues SET current_season = ?
            WHERE guild_id = ? AND is_active = 1
        ''', (year, interaction.guild_id))
        
        if cursor.rowcount > 0:
            conn.commit()
            await interaction.response.send_message(f"✅ Season set to **{year}**")
        else:
            await interaction.response.send_message("❌ No active league found.", ephemeral=True)
        
        conn.close()
    
    @league_group.command(name="remove", description="[Admin] Remove a league")
    @app_commands.describe(league="Select the league to remove")
    @app_commands.autocomplete(league=_league_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def league_remove(self, interaction: discord.Interaction, league: str):
        """Remove a league from this server."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT league_name FROM guild_leagues WHERE guild_id = ? AND league_id = ?',
                      (interaction.guild_id, league))
        row = cursor.fetchone()
        
        if not row:
            await interaction.response.send_message(f"❌ League '{league}' not found.", ephemeral=True)
            conn.close()
            return
        
        name = row[0]
        cursor.execute('DELETE FROM guild_leagues WHERE guild_id = ? AND league_id = ?',
                      (interaction.guild_id, league))
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(f"✅ Removed league **{name}** ({league})")
    
    @league_group.command(name="channels", description="[Admin] Set notification channels")
    @app_commands.describe(
        wagers="Channel for wager notifications",
        payouts="Channel for payout notifications",
        scores="Channel for score notifications",
        announcements="Channel for announcements",
        bestball="Channel for Best Ball notifications"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def league_channels(
        self,
        interaction: discord.Interaction,
        wagers: Optional[discord.TextChannel] = None,
        payouts: Optional[discord.TextChannel] = None,
        scores: Optional[discord.TextChannel] = None,
        announcements: Optional[discord.TextChannel] = None,
        bestball: Optional[discord.TextChannel] = None
    ):
        """Set channels for bot notifications."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO guild_channels (guild_id, wagers_channel_id, payouts_channel_id, 
                                        scores_channel_id, announcements_channel_id, bestball_channel_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                wagers_channel_id = COALESCE(excluded.wagers_channel_id, guild_channels.wagers_channel_id),
                payouts_channel_id = COALESCE(excluded.payouts_channel_id, guild_channels.payouts_channel_id),
                scores_channel_id = COALESCE(excluded.scores_channel_id, guild_channels.scores_channel_id),
                announcements_channel_id = COALESCE(excluded.announcements_channel_id, guild_channels.announcements_channel_id),
                bestball_channel_id = COALESCE(excluded.bestball_channel_id, guild_channels.bestball_channel_id)
        ''', (
            interaction.guild_id,
            wagers.id if wagers else None,
            payouts.id if payouts else None,
            scores.id if scores else None,
            announcements.id if announcements else None,
            bestball.id if bestball else None
        ))
        
        conn.commit()
        conn.close()
        
        updated = []
        if wagers: updated.append(f"Wagers: {wagers.mention}")
        if payouts: updated.append(f"Payouts: {payouts.mention}")
        if scores: updated.append(f"Scores: {scores.mention}")
        if announcements: updated.append(f"Announcements: {announcements.mention}")
        if bestball: updated.append(f"Best Ball: {bestball.mention}")
        
        if updated:
            await interaction.response.send_message(f"✅ Updated channels:\n" + "\n".join(updated))
        else:
            await interaction.response.send_message("❌ No channels specified.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LeagueConfigCog(bot))
"""
