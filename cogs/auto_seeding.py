"""
Auto Seeding Cog - Manage playoff seedings
Commands:
- /bulkseeding - Set multiple seedings at once
- /viewseedings - View current seedings
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import logging
from typing import Optional, List

logger = logging.getLogger('MistressLIV.AutoSeeding')

# AFC and NFC team lists
AFC_TEAMS = ['BAL', 'BUF', 'CIN', 'CLE', 'DEN', 'HOU', 'IND', 'JAX', 
             'KC', 'LAC', 'LV', 'MIA', 'NE', 'NYJ', 'PIT', 'TEN']
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR',
             'MIN', 'NO', 'NYG', 'PHI', 'SEA', 'SF', 'TB', 'WAS']


class AutoSeedingCog(commands.Cog):
    """Cog for managing playoff seedings."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
    
    def get_db_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def _get_team_owner(self, guild: discord.Guild, team_abbr: str) -> Optional[discord.Member]:
        """Find the Discord member who owns a team from the database registration."""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT user_discord_id FROM teams WHERE team_id = ?', (team_abbr.upper(),))
            result = cursor.fetchone()
            conn.close()
            if result and result[0]:
                return guild.get_member(result[0])
        except:
            pass
        return None
    
    @app_commands.command(name="bulkseeding", description="[Admin] Set multiple seedings at once from a list")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        conference="AFC or NFC",
        seedings="Comma-separated list of team abbreviations in seed order (1-16)"
    )
    async def bulk_seeding(
        self,
        interaction: discord.Interaction,
        season: int,
        conference: str,
        seedings: str
    ):
        """
        Set multiple seedings at once.
        Example: /bulkseeding 2027 NFC "LV,ATL,TEN,MIA,SEA,DAL,PHI,IND"
        """
        await interaction.response.defer(ephemeral=True)
        
        conference = conference.upper()
        if conference not in ['AFC', 'NFC']:
            await interaction.followup.send("Conference must be AFC or NFC", ephemeral=True)
            return
        
        # Parse the seedings list
        teams = [t.strip().upper() for t in seedings.split(',')]
        
        if len(teams) > 16:
            await interaction.followup.send("Maximum 16 seeds allowed", ephemeral=True)
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        results = []
        errors = []
        
        for seed, team_abbr in enumerate(teams, 1):
            # Validate team
            all_teams = AFC_TEAMS + NFC_TEAMS
            if team_abbr not in all_teams:
                errors.append(f"Seed {seed}: Unknown team '{team_abbr}'")
                continue
            
            # Find owner
            owner = self._get_team_owner(interaction.guild, team_abbr)
            user_id = owner.id if owner else None
            
            # Insert/update seeding
            cursor.execute('''
                INSERT OR REPLACE INTO season_standings 
                (season, conference, seed, team_id, user_discord_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (season, conference, seed, team_abbr, user_id))
            
            owner_name = owner.display_name if owner else "Unknown"
            results.append(f"#{seed}: {team_abbr} ({owner_name})")
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title=f"✅ {conference} Seedings Set for Season {season}",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Seedings",
            value="\n".join(results) if results else "None set",
            inline=False
        )
        
        if errors:
            embed.add_field(
                name="⚠️ Errors",
                value="\n".join(errors),
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="viewseedings", description="View current seedings for a season")
    @app_commands.describe(season="Season number")
    async def view_seedings(self, interaction: discord.Interaction, season: int):
        """View the current seedings for a season."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT conference, seed, team_id, user_discord_id
            FROM season_standings
            WHERE season = ?
            ORDER BY conference, seed
        ''', (season,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            await interaction.response.send_message(
                f"No seedings found for Season {season}",
                ephemeral=True
            )
            return
        
        afc_seedings = []
        nfc_seedings = []
        
        for conf, seed, team_id, user_id in rows:
            user = interaction.guild.get_member(user_id) if user_id else None
            user_name = user.display_name if user else "Unknown"
            line = f"#{seed}: {team_id} ({user_name})"
            
            if conf == 'AFC':
                afc_seedings.append(line)
            else:
                nfc_seedings.append(line)
        
        embed = discord.Embed(
            title=f"📊 Season {season} Seedings",
            color=discord.Color.blue()
        )
        
        if afc_seedings:
            embed.add_field(
                name="AFC",
                value="\n".join(afc_seedings[:8]),
                inline=True
            )
            if len(afc_seedings) > 8:
                embed.add_field(
                    name="AFC (cont.)",
                    value="\n".join(afc_seedings[8:]),
                    inline=True
                )
        
        if nfc_seedings:
            embed.add_field(
                name="NFC",
                value="\n".join(nfc_seedings[:8]),
                inline=True
            )
            if len(nfc_seedings) > 8:
                embed.add_field(
                    name="NFC (cont.)",
                    value="\n".join(nfc_seedings[8:]),
                    inline=True
                )
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(AutoSeedingCog(bot))
