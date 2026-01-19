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
import asyncio

logger = logging.getLogger('MistressLIV.Announcements')


class AnnouncementsCog(commands.Cog):
    """Cog for admin announcements and channel management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
    
    def get_db_connection(self):
        return sqlite3.connect(self.db_path)
    
    def get_registered_owners(self) -> list:
        """Get all registered team owners from the database."""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT team_id, team_name, user_discord_id FROM teams WHERE user_discord_id IS NOT NULL"
            )
            results = cursor.fetchall()
            conn.close()
            logger.info(f"Found {len(results)} registered team owners in database")
            return results
        except Exception as e:
            logger.error(f"Error getting registered owners: {e}")
            return []

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
        
        # DM all registered team owners from database
        registered_owners = self.get_registered_owners()
        dm_count = 0
        dm_failed = 0
        failed_members = []
        
        dm_embed = discord.Embed(
            title="📢 Mistress LIV Announcement",
            description=message,
            color=discord.Color.blue()
        )
        dm_embed.set_footer(text=f"From: {interaction.guild.name}")
        
        logger.info(f"Attempting to DM {len(registered_owners)} registered team owners")
        
        for team_id, team_name, discord_id in registered_owners:
            try:
                # fetch_user works without Server Members Intent
                user = await self.bot.fetch_user(discord_id)
                await user.send(embed=dm_embed)
                dm_count += 1
                logger.info(f"Successfully DMed {team_id} owner ({discord_id})")
                await asyncio.sleep(0.3)  # Rate limiting
            except discord.NotFound:
                dm_failed += 1
                failed_members.append(f"{team_id} (user not found)")
                logger.warning(f"User not found for {team_id}: {discord_id}")
            except discord.Forbidden:
                dm_failed += 1
                failed_members.append(f"{team_id} (DMs disabled)")
                logger.warning(f"Cannot DM {team_id} owner - DMs disabled")
            except Exception as e:
                dm_failed += 1
                failed_members.append(f"{team_id} ({str(e)[:20]})")
                logger.error(f"Failed to DM {team_id} owner: {e}")
        
        result = f"✅ Posted to: {', '.join(posted_to) if posted_to else 'No channels found'}"
        result += f"\n📬 DMed {dm_count} league members"
        if dm_failed > 0:
            result += f" ({dm_failed} failed)"
            if len(failed_members) <= 5:
                result += f"\nFailed: {', '.join(failed_members)}"
        
        if len(registered_owners) == 0:
            result += "\n\n⚠️ **No team owners registered!** Have owners run `/register` to sign up."
        
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
        
        # Get registered team owners from database
        registered_owners = self.get_registered_owners()
        
        embed = discord.Embed(
            title="📬 Message from Mistress LIV",
            description=message,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"From: {interaction.guild.name}")
        
        success = 0
        failed = 0
        failed_members = []
        
        logger.info(f"Attempting to DM {len(registered_owners)} registered team owners")
        
        for team_id, team_name, discord_id in registered_owners:
            try:
                # fetch_user works without Server Members Intent
                user = await self.bot.fetch_user(discord_id)
                await user.send(embed=embed)
                success += 1
                await asyncio.sleep(0.3)  # Rate limiting
            except discord.NotFound:
                failed += 1
                failed_members.append(f"{team_id} (user not found)")
            except discord.Forbidden:
                failed += 1
                failed_members.append(f"{team_id} (DMs disabled)")
            except Exception as e:
                failed += 1
                failed_members.append(f"{team_id}")
        
        result = f"✅ DMed {success} league members"
        if failed > 0:
            result += f" ({failed} failed)"
            if len(failed_members) <= 5:
                result += f"\nFailed: {', '.join(failed_members)}"
        
        if len(registered_owners) == 0:
            result += "\n\n⚠️ **No team owners registered!** Have owners run `/register` to sign up."
        
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
