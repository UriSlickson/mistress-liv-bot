"""
Announcements Cog - Admin announcement and channel management
COMMANDS:
/announce all - Post to #townsquare, #announcements, AND DM all members
/announce post - Post to #townsquare and #announcements only
/announce dm - DM all league members only
/announce clear - Clear a selected channel
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from typing import Optional
import logging

logger = logging.getLogger('MistressLIV.Announcements')


class AnnouncementsCog(commands.Cog):
    """Cog for admin announcements and channel management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
    
    def get_db_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _get_team_owners(self, guild: discord.Guild) -> list:
        """Get all members with team roles."""
        team_roles = ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 
                      'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
                      'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
                      'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS']
        
        owners = []
        for member in guild.members:
            if member.bot:
                continue
            for role in member.roles:
                if role.name.upper() in team_roles:
                    owners.append(member)
                    break
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
        
        # Post to announcements
        if announcements:
            await announcements.send(embed=embed)
            posted_to.append(announcements.mention)
        
        # DM all league members
        owners = self._get_team_owners(interaction.guild)
        dm_count = 0
        dm_failed = 0
        
        for owner in owners:
            try:
                await owner.send(embed=embed)
                dm_count += 1
            except:
                dm_failed += 1
        
        result = f"✅ Posted to: {', '.join(posted_to) if posted_to else 'No channels found'}"
        result += f"\n📬 DMed {dm_count} league members ({dm_failed} failed)"
        
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
        
        for owner in owners:
            try:
                await owner.send(embed=embed)
                success += 1
            except:
                failed += 1
        
        await interaction.followup.send(
            f"✅ DMed {success} league members ({failed} failed)",
            ephemeral=True
        )
    
    @announce_group.command(name="clear", description="Delete all messages in a selected channel")
    @app_commands.describe(
        channel="Channel to clear",
        confirm="Type CONFIRM to proceed"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def announce_clear(
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
