"""Recruitment Cog - Recruitment placeholder"""
import discord
from discord.ext import commands

class RecruitmentCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

async def setup(bot):
    await bot.add_cog(RecruitmentCog(bot))
