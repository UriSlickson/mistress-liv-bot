"""
Announcements Cog - Admin announcement and channel management
COMMANDS:
/announce all - Post to #townsquare, #announcements, AND DM all members
/announce post - Post to #townsquare and #announcements only
/announce dm - DM all league members only
/clearchannel - Clear a selected channel (standalone)
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from typing import Optional
import logging

logger = logging.getLogger('MistressLIV.Announcements')

# Team abbreviations and full names for matching
TEAM_IDENTIFIERS = {
    'ARI': ['ARI', 'CARDINALS', 'ARIZONA'],
    'ATL': ['ATL', 'FALCONS', 'ATLANTA'],
    'BAL': ['BAL', 'RAVENS', 'BALTIMORE'],
    'BUF': ['BUF', 'BILLS', 'BUFFALO'],
    'CAR': ['CAR', 'PANTHERS', 'CAROLINA'],
    'CHI': ['CHI', 'BEARS', 'CHICAGO'],
    'CIN': ['CIN', 'BENGALS', 'CINCINNATI'],
    'CLE': ['CLE', 'BROWNS', 'CLEVELAND'],
    'DAL': ['DAL', 'COWBOYS', 'DALLAS'],
    'DEN': ['DEN', 'BRONCOS', 'DENVER'],
    'DET': ['DET', 'LIONS', 'DETROIT'],
    'GB': ['GB', 'PACKERS', 'GREEN BAY', 'GREENBAY'],
    'HOU': ['HOU', 'TEXANS', 'HOUSTON'],
    'IND': ['IND', 'COLTS', 'INDIANAPOLIS'],
    'JAX': ['JAX', 'JAGUARS', 'JACKSONVILLE'],
    'KC': ['KC', 'CHIEFS', 'KANSAS CITY', 'KANSASCITY'],
    'LAC': ['LAC', 'CHARGERS', 'LA CHARGERS'],
    'LAR': ['LAR', 'RAMS', 'LA RAMS'],
    'LV': ['LV', 'RAIDERS', 'LAS VEGAS', 'LASVEGAS'],
    'MIA': ['MIA', 'DOLPHINS', 'MIAMI'],
    'MIN': ['MIN', 'VIKINGS', 'MINNESOTA'],
    'NE': ['NE', 'PATRIOTS', 'NEW ENGLAND', 'NEWENGLAND'],
    'NO': ['NO', 'SAINTS', 'NEW ORLEANS', 'NEWORLEANS'],
    'NYG': ['NYG', 'GIANTS', 'NY GIANTS'],
    'NYJ': ['NYJ', 'JETS', 'NY JETS'],
    'PHI': ['PHI', 'EAGLES', 'PHILADELPHIA'],
    'PIT': ['PIT', 'STEELERS', 'PITTSBURGH'],
    'SEA': ['SEA', 'SEAHAWKS', 'SEATTLE'],
    'SF': ['SF', '49ERS', 'NINERS', 'SAN FRANCISCO', 'SANFRANCISCO'],
    'TB': ['TB', 'BUCCANEERS', 'BUCS', 'TAMPA BAY', 'TAMPABAY'],
    'TEN': ['TEN', 'TITANS', 'TENNESSEE'],
    'WAS': ['WAS', 'COMMANDERS', 'WASHINGTON'],
}


class AnnouncementsCog(commands.Cog):
    """Cog for admin announcements and channel management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
    
    def get_db_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _is_team_role(self, role_name: str) -> bool:
        """Check if a role name matches any team identifier."""
        role_upper = role_name.upper()
        for team, identifiers in TEAM_IDENTIFIERS.items():
            for identifier in identifiers:
                if identifier in role_upper or role_upper in identifier:
                    return True
        return False
    
    def _get_team_owners(self, guild: discord.Guild) -> list:
        """Get all members with team roles."""
        owners = []
        for member in guild.members:
            if member.bot:
                continue
            for role in member.roles:
                if self._is_team_role(role.name):
                    owners.append(member)
                    break
        
        logger.info(f"Found {len(owners)} team owners in {guild.name}")
        return owners

    # ==================== ANNOUNCE COMMAND GROUP ====================
    
    announce_group = app_commands.Group(name="announce", description="Announcement commands (Admin)")
    
    @announce_group.command(name="all", description="Post to #townsquare, #announcements, AND DM all league members")
    @app_commands.describe(message="The announcement message")
    @app_commands.checks.has_permissions(administrator=True)
    async def announce_all(self, interaction: discord.Interaction, message: str):
        """Post announcement to channels AND DM all league members."""
        await interaction.response.defer()
        
        # Find channels
        townsquare = discord.utils.get(interaction.guild.text_channels, name='townsquare')
        announcements = discord.utils.get(interaction.guild.text_channels, name='announcements')
        
        embed = discord.Embed(
            title="📢 Announcement",
            description=message,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Posted by {interaction.user.display_name}")
        
        posted_to = []
        
        # Post to townsquare
        if townsquare:
            await townsquare.send(embed=embed)
            posted_to.append(townsquare.mention)
            logger.info(f"Posted announcement to #townsquare")
        else:
            logger.warning("Could not find #townsquare channel")
        
        # Post to announcements
        if announcements:
            await announcements.send(embed=embed)
            posted_to.append(announcements.mention)
            logger.info(f"Posted announcement to #announcements")
        else:
            logger.warning("Could not find #announcements channel")
        
        # DM all league members
        owners = self._get_team_owners(interaction.guild)
        dm_count = 0
        dm_failed = 0
        failed_members = []
        
        logger.info(f"Attempting to DM {len(owners)} team owners")
        
        for owner in owners:
            try:
                await owner.send(embed=embed)
                dm_count += 1
                logger.info(f"Successfully DMed {owner.display_name}")
            except discord.Forbidden:
                dm_failed += 1
                failed_members.append(f"{owner.display_name} (DMs disabled)")
                logger.warning(f"Cannot DM {owner.display_name} - DMs disabled")
            except Exception as e:
                dm_failed += 1
                failed_members.append(f"{owner.display_name} ({str(e)[:20]})")
                logger.error(f"Failed to DM {owner.display_name}: {e}")
        
        result = f"✅ Posted to: {', '.join(posted_to) if posted_to else 'No channels found'}"
        result += f"\n📬 DMed {dm_count} league members"
        if dm_failed > 0:
            result += f" ({dm_failed} failed)"
            if len(failed_members) <= 5:
                result += f"\nFailed: {', '.join(failed_members)}"
        
        await interaction.followup.send(result, ephemeral=True)
    
    @announce_group.command(name="post", description="Post to #townsquare and #announcements only")
    @app_commands.describe(message="The announcement message")
    @app_commands.checks.has_permissions(administrator=True)
    async def announce_post(self, interaction: discord.Interaction, message: str):
        """Post announcement to #townsquare and #announcements only."""
        await interaction.response.defer()
        
        # Find channels
        townsquare = discord.utils.get(interaction.guild.text_channels, name='townsquare')
        announcements = discord.utils.get(interaction.guild.text_channels, name='announcements')
        
        embed = discord.Embed(
            title="📢 Announcement",
            description=message,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Posted by {interaction.user.display_name}")
        
        posted_to = []
        
        # Post to townsquare
        if townsquare:
            await townsquare.send(embed=embed)
            posted_to.append(townsquare.mention)
        
        # Post to announcements
        if announcements:
            await announcements.send(embed=embed)
            posted_to.append(announcements.mention)
        
        if posted_to:
            await interaction.followup.send(f"✅ Posted to: {', '.join(posted_to)}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Could not find #townsquare or #announcements channels", ephemeral=True)
    
    @announce_group.command(name="dm", description="DM all league members only")
    @app_commands.describe(message="The message to send")
    @app_commands.checks.has_permissions(administrator=True)
    async def announce_dm(self, interaction: discord.Interaction, message: str):
        """DM all league members."""
        await interaction.response.defer()
        
        owners = self._get_team_owners(interaction.guild)
        
        embed = discord.Embed(
            title="📬 Message from Mistress LIV",
            description=message,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"From {interaction.user.display_name}")
        
        success = 0
        failed = 0
        failed_members = []
        
        logger.info(f"Attempting to DM {len(owners)} team owners")
        
        for owner in owners:
            try:
                await owner.send(embed=embed)
                success += 1
            except discord.Forbidden:
                failed += 1
                failed_members.append(f"{owner.display_name} (DMs disabled)")
            except Exception as e:
                failed += 1
                failed_members.append(f"{owner.display_name}")
        
        result = f"✅ DMed {success} league members"
        if failed > 0:
            result += f" ({failed} failed)"
            if len(failed_members) <= 5:
                result += f"\nFailed: {', '.join(failed_members)}"
        
        await interaction.followup.send(result, ephemeral=True)

    # ==================== STANDALONE COMMANDS ====================
    
    @app_commands.command(name="clearchannel", description="[Admin] Delete all messages in a selected channel")
    @app_commands.describe(
        channel="Channel to clear",
        confirm="Type CONFIRM to proceed"
    )
    @app_commands.default_permissions(administrator=True)
    async def clear_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        confirm: str
    ):
        """Clear all messages in a selected channel."""
        if confirm != "CONFIRM":
            await interaction.response.send_message(
                "❌ You must type CONFIRM to clear the channel.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        deleted = 0
        async for message in channel.history(limit=None):
            try:
                await message.delete()
                deleted += 1
            except:
                pass
        
        await interaction.followup.send(
            f"✅ Deleted {deleted} messages from {channel.mention}",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(AnnouncementsCog(bot))
