"""
Auto Seeding Cog - Automatically import playoff seedings from MyMadden website
Features:
- Import seedings from MyMadden standings page
- Map teams to registered Discord users
- Detect Super Bowl completion and prompt for import
- Auto-populate all AFC/NFC seedings
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import asyncio
import re
import logging
from typing import Optional, List, Dict
from datetime import datetime

logger = logging.getLogger('MistressLIV.AutoSeeding')

# Team ID to name mapping (from MyMadden logo URLs)
TEAM_ID_TO_NAME = {
    '0': 'unknown', '1': 'bears', '2': 'bengals', '3': 'bills', '4': 'broncos',
    '5': 'browns', '6': 'buccaneers', '7': 'cardinals', '8': 'chargers',
    '9': 'chiefs', '10': 'colts', '11': 'commanders', '12': 'cowboys',
    '13': 'dolphins', '14': 'eagles', '15': 'falcons', '16': 'giants',
    '17': 'jaguars', '18': 'jets', '19': 'lions', '20': 'packers',
    '21': 'panthers', '22': 'patriots', '23': 'raiders', '24': 'rams',
    '25': 'ravens', '26': 'saints', '27': 'seahawks', '28': 'steelers',
    '29': 'texans', '30': 'titans', '31': '49ers', '32': 'vikings'
}

TEAM_NAME_TO_ABBR = {
    'cardinals': 'ARI', 'falcons': 'ATL', 'ravens': 'BAL', 'bills': 'BUF',
    'panthers': 'CAR', 'bears': 'CHI', 'bengals': 'CIN', 'browns': 'CLE',
    'cowboys': 'DAL', 'broncos': 'DEN', 'lions': 'DET', 'packers': 'GB',
    'texans': 'HOU', 'colts': 'IND', 'jaguars': 'JAX', 'chiefs': 'KC',
    'chargers': 'LAC', 'rams': 'LAR', 'raiders': 'LV', 'dolphins': 'MIA',
    'vikings': 'MIN', 'patriots': 'NE', 'saints': 'NO', 'giants': 'NYG',
    'jets': 'NYJ', 'eagles': 'PHI', 'steelers': 'PIT', 'seahawks': 'SEA',
    '49ers': 'SF', 'buccaneers': 'TB', 'titans': 'TEN', 'commanders': 'WAS'
}

# AFC and NFC team lists
AFC_TEAMS = ['BAL', 'BUF', 'CIN', 'CLE', 'DEN', 'HOU', 'IND', 'JAX', 
             'KC', 'LAC', 'LV', 'MIA', 'NE', 'NYJ', 'PIT', 'TEN']
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR',
             'MIN', 'NO', 'NYG', 'PHI', 'SEA', 'SF', 'TB', 'WAS']


class AutoSeedingCog(commands.Cog):
    """Cog for automatic seeding import from MyMadden."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self.pending_super_bowl_import = {}  # Track seasons pending import
    
    def get_db_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def _get_team_owner(self, guild: discord.Guild, team_abbr: str) -> Optional[discord.Member]:
        """Find the Discord member who owns a team based on their role."""
        for member in guild.members:
            for role in member.roles:
                if role.name.upper() == team_abbr.upper():
                    return member
        return None
    
    def _get_registered_user_for_team(self, team_abbr: str) -> Optional[int]:
        """Get the registered Discord user ID for a team from the database."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if there's a registration table
        try:
            cursor.execute('''
                SELECT user_discord_id FROM team_registrations 
                WHERE team_id = ? ORDER BY registered_at DESC LIMIT 1
            ''', (team_abbr.upper(),))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except sqlite3.OperationalError:
            conn.close()
            return None
    
    def _parse_standings_from_message(self, content: str) -> Dict[str, List[Dict]]:
        """
        Parse standings data from a formatted message or embed.
        This is used when standings are posted to Discord.
        """
        # This would parse standings from a Discord message if needed
        pass
    
    @app_commands.command(name="importseedings", description="[Admin] Import seedings from MyMadden for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number to import seedings for"
    )
    async def import_seedings(self, interaction: discord.Interaction, season: int):
        """
        Import all seedings from MyMadden website.
        Since we can't scrape the rendered page directly, this command
        provides a guided import process.
        """
        await interaction.response.defer(ephemeral=True)
        
        # Create an embed with instructions
        embed = discord.Embed(
            title=f"📊 Import Seedings for Season {season}",
            description=(
                "To import seedings, I'll need the standings data from MyMadden.\n\n"
                "**Option 1: Auto-detect from team roles**\n"
                "I can map teams to users based on their team roles.\n\n"
                "**Option 2: Manual entry**\n"
                "Use `/setseeding` for each seed individually.\n\n"
                "Would you like me to scan team roles and show the current team-to-user mapping?"
            ),
            color=discord.Color.blue()
        )
        
        # Create buttons for the options
        view = SeedingImportView(self, interaction.guild, season)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="scanteams", description="[Admin] Scan and display team-to-user mapping")
    @app_commands.default_permissions(administrator=True)
    async def scan_teams(self, interaction: discord.Interaction):
        """Scan all members and show their team assignments."""
        await interaction.response.defer(ephemeral=True)
        
        afc_mapping = []
        nfc_mapping = []
        unassigned_teams = []
        
        for team_abbr in AFC_TEAMS:
            owner = self._get_team_owner(interaction.guild, team_abbr)
            if owner:
                afc_mapping.append(f"{team_abbr}: {owner.display_name}")
            else:
                unassigned_teams.append(team_abbr)
        
        for team_abbr in NFC_TEAMS:
            owner = self._get_team_owner(interaction.guild, team_abbr)
            if owner:
                nfc_mapping.append(f"{team_abbr}: {owner.display_name}")
            else:
                unassigned_teams.append(team_abbr)
        
        embed = discord.Embed(
            title="🏈 Team-to-User Mapping",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="AFC Teams",
            value="\n".join(afc_mapping) if afc_mapping else "No AFC teams assigned",
            inline=True
        )
        
        embed.add_field(
            name="NFC Teams",
            value="\n".join(nfc_mapping) if nfc_mapping else "No NFC teams assigned",
            inline=True
        )
        
        if unassigned_teams:
            embed.add_field(
                name="⚠️ Unassigned Teams",
                value=", ".join(unassigned_teams),
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
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
        Example: /bulkseeding 2027 NFC "LV,ATL,TEN,MIA,SEA,DAL,PHI,IND,GB,NO,TB,MIN,CLE,DET,NYJ,BAL"
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
                value="\n".join(afc_seedings[:8]),  # First 8
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
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for Super Bowl results in #scores channel."""
        # Skip bot messages (except MyMadden bot)
        if message.author.bot and 'mymadden' not in message.author.name.lower():
            return
        
        # Check if this is in #scores channel
        if message.channel.name != 'scores':
            return
        
        # Check if this is a Super Bowl game
        content = message.content.lower()
        if 'super bowl' in content or 'superbowl' in content:
            # Extract season year from the message
            year_match = re.search(r'(\d{4})', message.content)
            if year_match:
                season = int(year_match.group(1))
                
                # Notify admins that Super Bowl is complete
                logger.info(f"Super Bowl detected for season {season}")
                
                # Find an admin channel to notify
                for channel in message.guild.text_channels:
                    if 'admin' in channel.name.lower() or 'mod' in channel.name.lower():
                        embed = discord.Embed(
                            title="🏆 Super Bowl Complete!",
                            description=(
                                f"The Super Bowl for Season {season} has been played!\n\n"
                                f"**Next Steps:**\n"
                                f"1. Use `/bulkseeding` to set AFC and NFC seedings\n"
                                f"2. Use `/setplayoffwinner` to record playoff winners\n"
                                f"3. Use `/generatepayments` to create payment obligations\n\n"
                                f"Or use `/viewseedings {season}` to check current seedings."
                            ),
                            color=discord.Color.gold()
                        )
                        try:
                            await channel.send(embed=embed)
                        except discord.Forbidden:
                            pass
                        break


class SeedingImportView(discord.ui.View):
    """View with buttons for seeding import options."""
    
    def __init__(self, cog: AutoSeedingCog, guild: discord.Guild, season: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.season = season
    
    @discord.ui.button(label="Scan Team Roles", style=discord.ButtonStyle.primary)
    async def scan_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Scan team roles and show mapping."""
        afc_mapping = []
        nfc_mapping = []
        
        for team_abbr in AFC_TEAMS:
            owner = self.cog._get_team_owner(self.guild, team_abbr)
            if owner:
                afc_mapping.append(f"{team_abbr}: {owner.display_name}")
            else:
                afc_mapping.append(f"{team_abbr}: ❌ Unassigned")
        
        for team_abbr in NFC_TEAMS:
            owner = self.cog._get_team_owner(self.guild, team_abbr)
            if owner:
                nfc_mapping.append(f"{team_abbr}: {owner.display_name}")
            else:
                nfc_mapping.append(f"{team_abbr}: ❌ Unassigned")
        
        embed = discord.Embed(
            title="🏈 Current Team Assignments",
            description=(
                f"Use `/bulkseeding` to set seedings in order.\n\n"
                f"**Example:**\n"
                f"`/bulkseeding {self.season} AFC NE,PIT,CAR,NYG,LAR,BUF,JAX,DEN,...`"
            ),
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="AFC Teams",
            value="\n".join(afc_mapping[:8]),
            inline=True
        )
        embed.add_field(
            name="AFC (cont.)",
            value="\n".join(afc_mapping[8:]),
            inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(
            name="NFC Teams",
            value="\n".join(nfc_mapping[:8]),
            inline=True
        )
        embed.add_field(
            name="NFC (cont.)",
            value="\n".join(nfc_mapping[8:]),
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(AutoSeedingCog(bot))
