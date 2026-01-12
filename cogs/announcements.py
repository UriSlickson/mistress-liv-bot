"""
Announcements Cog - Admin announcement and channel management
CONSOLIDATED COMMANDS:
/announce post - Post to channels and optionally DM owners
/announce dm - DM all team owners
/announce clear - Clear a channel
/announce commands - Post command list
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
    
    @announce_group.command(name="post", description="Post announcement to channels and optionally DM owners")
    @app_commands.describe(
        message="The announcement message",
        dm_owners="Also DM all team owners (default: False)",
        channel="Specific channel to post to (default: #townsquare)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def announce_post(
        self,
        interaction: discord.Interaction,
        message: str,
        dm_owners: bool = False,
        channel: Optional[discord.TextChannel] = None
    ):
        """Post announcement to channels and optionally DM owners."""
        await interaction.response.defer()
        
        # Find channels
        townsquare = discord.utils.get(interaction.guild.text_channels, name='townsquare')
        announcements = discord.utils.get(interaction.guild.text_channels, name='announcements')
        target_channel = channel or townsquare
        
        embed = discord.Embed(
            title="📢 Announcement",
            description=message,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Posted by {interaction.user.display_name}")
        
        posted_to = []
        
        # Post to target channel
        if target_channel:
            await target_channel.send(embed=embed)
            posted_to.append(target_channel.mention)
        
        # Also post to announcements if different
        if announcements and announcements != target_channel:
            await announcements.send(embed=embed)
            posted_to.append(announcements.mention)
        
        dm_count = 0
        dm_failed = 0
        
        if dm_owners:
            owners = self._get_team_owners(interaction.guild)
            for owner in owners:
                try:
                    await owner.send(embed=embed)
                    dm_count += 1
                except:
                    dm_failed += 1
        
        result = f"✅ Posted to: {', '.join(posted_to)}"
        if dm_owners:
            result += f"\n📬 DMed {dm_count} owners ({dm_failed} failed)"
        
        await interaction.followup.send(result, ephemeral=True)
    
    @announce_group.command(name="dm", description="Send a DM to all team owners")
    @app_commands.describe(message="The message to send")
    @app_commands.checks.has_permissions(administrator=True)
    async def announce_dm(self, interaction: discord.Interaction, message: str):
        """DM all team owners."""
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
            f"✅ DMed {success} team owners ({failed} failed)",
            ephemeral=True
        )
    
    @announce_group.command(name="clear", description="Delete all messages in a channel")
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
        """Clear all messages in a channel."""
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
    
    @announce_group.command(name="commands", description="Post the command list to a channel")
    @app_commands.describe(channel="Channel to post to (default: #commands)")
    @app_commands.checks.has_permissions(administrator=True)
    async def announce_commands(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None
    ):
        """Post the full command list to a channel."""
        await interaction.response.defer()
        
        target = channel or discord.utils.get(interaction.guild.text_channels, name='commands')
        
        if not target:
            await interaction.followup.send("❌ No #commands channel found.", ephemeral=True)
            return
        
        # Command list embed
        embed = discord.Embed(
            title="📋 Mistress LIV Bot Commands",
            description="All available commands organized by category",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="💰 Wagers",
            value=(
                "`/wager` - Create a wager\n"
                "`/acceptwager` - Accept a wager\n"
                "`/declinewager` - Decline a wager\n"
                "`/cancelwager` - Cancel your wager\n"
                "`/wagerwin` - Settle a wager\n"
                "`/paid` - Confirm payment received\n"
                "`/mywagers` - View your wagers"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💵 Payments",
            value=(
                "`/payments owedtome` - Who owes you\n"
                "`/payments iowe` - Who you owe\n"
                "`/payments status` - Your payment status\n"
                "`/payments paid` - Mark payment received"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🏈 Best Ball",
            value=(
                "`/bestball start` - Create event\n"
                "`/bestball join` - Join event\n"
                "`/bestball roster` - View your roster\n"
                "`/bestball add` - Add player\n"
                "`/bestball remove` - Remove player\n"
                "`/bestball status` - View standings\n"
                "`/bestball rules` - View rules"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 Leaderboards",
            value=(
                "`/leaderboard earners` - Top earners\n"
                "`/leaderboard losers` - Biggest losers\n"
                "`/wagerboard` - Wager leaderboard"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📜 League Info",
            value=(
                "`/rules` - League rules\n"
                "`/dynamics` - League dynamics\n"
                "`/requirements` - Member requirements\n"
                "`/payouts` - Payout structure"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ League Config",
            value=(
                "`/league setup` - Set up league\n"
                "`/league info` - View league info\n"
                "`/league switch` - Switch leagues"
            ),
            inline=False
        )
        
        await target.send(embed=embed)
        await interaction.followup.send(f"✅ Posted commands to {target.mention}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AnnouncementsCog(bot))
"""
