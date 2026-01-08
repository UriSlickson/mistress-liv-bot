"""Wagers Cog - Wager tracking placeholder"""
import discord
from discord.ext import commands

class WagersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

async def setup(bot):
    await bot.add_cog(WagersCog(bot))
