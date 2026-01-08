"""
Conversations Cog - Handles conversation tracking and management
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger('MistressLIV')


class Conversations(commands.Cog):
    """Cog for managing conversations and interactions"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Conversations cog loaded successfully!")


async def setup(bot):
    await bot.add_cog(Conversations(bot))
