"""
Command Guide Cog - Post comprehensive command instructions to #commands channel
Organized by action type with detailed usage instructions
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger('MistressLIV.CommandGuide')


class CommandGuideCog(commands.Cog):
    """Cog for posting comprehensive command guides."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="postguide", description="[Admin] Post comprehensive command guide to #commands channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to post the guide to (defaults to #commands)")
    async def post_guide(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Post the full command guide to the specified channel."""
        await interaction.response.defer(thinking=True)
        
        # Find #commands channel if not specified
        if not channel:
            channel = discord.utils.get(interaction.guild.text_channels, name='commands')
            if not channel:
                await interaction.followup.send("❌ Could not find #commands channel. Please specify a channel.", ephemeral=True)
                return
        
        try:
            # Post each section as a separate embed
            embeds_posted = 0
            
            # =====================
            # HEADER / INTRO
            # =====================
            intro_embed = discord.Embed(
                title="📖 Mistress LIV Bot - Complete Command Guide",
                description=(
                    "Welcome to the official command guide for **Mistress LIV Bot**!\n\n"
                    "This guide covers all available commands organized by action type. "
                    "Use `/` to access slash commands.\n\n"
                    "**Quick Reference:** Type `!commands` for a condensed command list."
                ),
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            intro_embed.set_footer(text="Mistress LIV Bot • Command Guide")
            await channel.send(embed=intro_embed)
            embeds_posted += 1
            
            # =====================
            # WAGERS SECTION
            # =====================
            wager_embed = discord.Embed(
                title="🎰 Making Wagers",
                description="Create and manage wagers with other league members on any game.",
                color=discord.Color.purple()
            )
            
            wager_embed.add_field(
                name="📝 Creating a Wager",
                value=(
                    "**Command:** `/wager`\n\n"
                    "**Parameters:**\n"
                    "• `opponent` - The person you want to bet against\n"
                    "• `amount` - The wager amount (e.g., $5, $10)\n"
                    "• `your_pick` - The team YOU think will win\n"
                    "• `opponent_pick` - The team your opponent gets\n"
                    "• `week` - The week number of the game\n"
                    "• `season` - The season number (optional)\n\n"
                    "**Example:** `/wager @JohnDoe 10 KC BUF 15`\n"
                    "*You bet $10 that KC beats BUF in Week 15*"
                ),
                inline=False
            )
            
            wager_embed.add_field(
                name="✅ Accepting/Declining Wagers",
                value=(
                    "When someone creates a wager with you, you'll be notified.\n\n"
                    "**Accept:** `/acceptwager wager_id`\n"
                    "**Decline:** `/declinewager wager_id`\n\n"
                    "*The wager ID is shown in the notification*"
                ),
                inline=False
            )
            
            wager_embed.add_field(
                name="📋 Viewing Your Wagers",
                value=(
                    "**Your wagers:** `/mywagers`\n"
                    "Shows all your pending, active, and completed wagers.\n\n"
                    "**Pending wagers:** `/pendingwagers`\n"
                    "Shows wagers waiting for game results.\n\n"
                    "**Leaderboard:** `/wagerboard`\n"
                    "See who's winning and losing the most in wagers."
                ),
                inline=False
            )
            
            wager_embed.add_field(
                name="🏆 Settling Wagers",
                value=(
                    "**Auto-Settlement:** Wagers are automatically settled when "
                    "game scores are posted in #scores by MyMadden bot.\n\n"
                    "**Manual Claim:** `/wagerwin wager_id winning_team`\n"
                    "Claim victory if auto-settlement didn't trigger.\n\n"
                    "**Check Score:** `/checkscore away_team home_team week`\n"
                    "Manually check a game result from MyMadden website."
                ),
                inline=False
            )
            
            wager_embed.add_field(
                name="💵 Marking Wagers Paid",
                value=(
                    "**Command:** `/markwagerpaid wager_id`\n\n"
                    "After paying the winner, use this command to mark it complete. "
                    "Only the winner can confirm payment received."
                ),
                inline=False
            )
            
            wager_embed.add_field(
                name="❌ Canceling Wagers",
                value=(
                    "**Command:** `/cancelwager wager_id`\n\n"
                    "Cancel a wager you created before it's accepted."
                ),
                inline=False
            )
            
            await channel.send(embed=wager_embed)
            embeds_posted += 1
            
            # =====================
            # SEASON END PAYOUTS
            # =====================
            payout_embed = discord.Embed(
                title="💰 Season End Payouts",
                description="Understanding how playoff earnings and payments work.",
                color=discord.Color.green()
            )
            
            payout_embed.add_field(
                name="🏆 Playoff Payout Values",
                value=(
                    "**Wild Card/Bye Win:** $50\n"
                    "**Divisional Win:** $100\n"
                    "**Conference Championship:** $200\n"
                    "**Super Bowl Win:** $300\n\n"
                    "*Maximum possible: $650 (winning all rounds)*"
                ),
                inline=False
            )
            
            payout_embed.add_field(
                name="📤 NFC Pot System (Seeds 8-16)",
                value=(
                    "NFC Seeds 8-16 pay into the pot:\n\n"
                    "• **#15, #16:** $100 each → Wildcard Winners\n"
                    "• **#13, #14:** $100 each → Divisional Winners\n"
                    "• **#11, #12:** $100 each → Conference Winner\n"
                    "• **#8, #9, #10:** $100 each → Super Bowl Winner"
                ),
                inline=False
            )
            
            payout_embed.add_field(
                name="🔗 AFC/NFC Seed Pairing (Seeds 1-7)",
                value=(
                    "Each NFC playoff seed is paired with the same AFC seed.\n\n"
                    "**When AFC team earns playoff money:**\n"
                    "• AFC owner keeps: **20%** of earnings\n"
                    "• NFC paired owner keeps: **80%** of AFC earnings\n"
                    "• NFC seed pays their paired AFC seed the 20%\n\n"
                    "**Example:** AFC #3 wins Divisional ($100)\n"
                    "→ AFC #3 gets $20, NFC #3 keeps $80, NFC pays AFC $20"
                ),
                inline=False
            )
            
            payout_embed.add_field(
                name="📊 Viewing Payouts",
                value=(
                    "**View payout rules:** `/payoutstructure`\n"
                    "**View seed pairings:** `/viewpairings [season]`\n"
                    "**League profitability:** `/profitability [season]`\n"
                    "**Your profitability:** `/myprofit`"
                ),
                inline=False
            )
            
            await channel.send(embed=payout_embed)
            embeds_posted += 1
            
            # =====================
            # PAYMENTS & DUES
            # =====================
            payment_embed = discord.Embed(
                title="💵 Payments & Dues",
                description="Track who owes you money and who you owe.",
                color=discord.Color.blue()
            )
            
            payment_embed.add_field(
                name="👀 Viewing Payments",
                value=(
                    "**Your summary:** `/mypayments`\n"
                    "Complete overview of what you owe and what's owed to you.\n\n"
                    "**Who owes you:** `/whooowesme`\n"
                    "See all unpaid debts owed TO you.\n\n"
                    "**Who you owe:** `/whoiowe`\n"
                    "See all unpaid debts YOU owe.\n\n"
                    "**All payments:** `/paymentschedule [season]`\n"
                    "View all outstanding payments league-wide."
                ),
                inline=False
            )
            
            payment_embed.add_field(
                name="✅ Marking Payments",
                value=(
                    "**Command:** `/markpaid debtor creditor amount`\n\n"
                    "**Parameters:**\n"
                    "• `debtor` - The person who paid\n"
                    "• `creditor` - The person who received payment\n"
                    "• `amount` - The amount paid\n\n"
                    "**Example:** `/markpaid @JohnDoe @JaneSmith 50`"
                ),
                inline=False
            )
            
            payment_embed.add_field(
                name="🏆 Leaderboards",
                value=(
                    "**Top earners:** `/topearners [season]`\n"
                    "Who's made the most money overall.\n\n"
                    "**Top losers:** `/toplosers [season]`\n"
                    "Who's lost the most money overall."
                ),
                inline=False
            )
            
            await channel.send(embed=payment_embed)
            embeds_posted += 1
            
            # =====================
            # REGISTRATION
            # =====================
            reg_embed = discord.Embed(
                title="📝 Registration",
                description="Register as a team owner to receive announcements and get your helmet emoji.",
                color=discord.Color.teal()
            )
            
            reg_embed.add_field(
                name="🏈 Registering",
                value=(
                    "**Command:** `/register`\n\n"
                    "Registers you as a team owner based on your team role. "
                    "This enables:\n"
                    "• Receiving league announcements via DM\n"
                    "• Automatic helmet emoji sync on your nickname\n"
                    "• Proper tracking in payment/wager systems"
                ),
                inline=False
            )
            
            reg_embed.add_field(
                name="🚪 Unregistering",
                value=(
                    "**Command:** `/unregister`\n\n"
                    "Remove yourself from the team owner list."
                ),
                inline=False
            )
            
            await channel.send(embed=reg_embed)
            embeds_posted += 1
            
            # =====================
            # PROFITABILITY
            # =====================
            profit_embed = discord.Embed(
                title="📊 Profitability Tracking",
                description="Track your franchise's financial performance across seasons.",
                color=discord.Color.gold()
            )
            
            profit_embed.add_field(
                name="📈 Viewing Profitability",
                value=(
                    "**League rankings:** `/profitability [season]`\n"
                    "See how everyone ranks in net profit.\n\n"
                    "**Your breakdown:** `/myprofit`\n"
                    "Detailed view of your earnings, dues, and wager profits.\n\n"
                    "**Payout structure:** `/payoutstructure`\n"
                    "Complete explanation of how payouts work.\n\n"
                    "**Seed pairings:** `/viewpairings [season]`\n"
                    "View AFC/NFC seed pairings and earnings."
                ),
                inline=False
            )
            
            profit_embed.add_field(
                name="💡 Understanding Net Profit",
                value=(
                    "**Net Profit** = Playoff Earnings - Dues Paid + Wager Profit\n\n"
                    "• **Playoff Earnings:** Money received from playoff wins\n"
                    "• **Dues Paid:** Money owed as a lower NFC seed\n"
                    "• **Wager Profit:** Net from wager wins minus losses"
                ),
                inline=False
            )
            
            await channel.send(embed=profit_embed)
            embeds_posted += 1
            
            # =====================
            # FUN COMMANDS
            # =====================
            fun_embed = discord.Embed(
                title="😤 Fun Commands",
                description="Track who complains the most in the league!",
                color=discord.Color.orange()
            )
            
            fun_embed.add_field(
                name="🏆 Whiner Leaderboard",
                value=(
                    "**Command:** `/whiner [timeframe]`\n\n"
                    "See who complains the most! Tracks keywords like:\n"
                    "*\"bs\", \"rigged\", \"unfair\", \"cheese\", \"glitch\"*, etc.\n\n"
                    "**Timeframes:** `all`, `week`, `month`, `season`"
                ),
                inline=False
            )
            
            fun_embed.add_field(
                name="📊 Your Stats",
                value=(
                    "**Command:** `/mywhines`\n\n"
                    "See your own complaint statistics."
                ),
                inline=False
            )
            
            await channel.send(embed=fun_embed)
            embeds_posted += 1
            
            # =====================
            # INFO COMMANDS
            # =====================
            info_embed = discord.Embed(
                title="ℹ️ Info Commands",
                description="General information and help commands.",
                color=discord.Color.blurple()
            )
            
            info_embed.add_field(
                name="📖 Help & Info",
                value=(
                    "**Help:** `/help`\n"
                    "View command categories and descriptions.\n\n"
                    "**Quick commands:** `!commands`\n"
                    "Condensed list of all commands.\n\n"
                    "**Server info:** `/serverinfo`\n"
                    "View server statistics.\n\n"
                    "**Bot latency:** `/ping`\n"
                    "Check if the bot is responsive."
                ),
                inline=False
            )
            
            await channel.send(embed=info_embed)
            embeds_posted += 1
            
            # =====================
            # ADMIN COMMANDS
            # =====================
            admin_embed = discord.Embed(
                title="🔧 Admin Commands",
                description="Commands for league administrators only.",
                color=discord.Color.red()
            )
            
            admin_embed.add_field(
                name="📢 Announcements",
                value=(
                    "**Post announcement:** `/announce message channels`\n"
                    "**DM all owners:** `/dmowners message`\n"
                    "**Post command list:** `/postcommands channel`\n"
                    "**Post this guide:** `/postguide channel`"
                ),
                inline=False
            )
            
            admin_embed.add_field(
                name="💰 Season End Setup",
                value=(
                    "**1. Set seedings:** `/setseeding season conference seed user`\n"
                    "Set AFC/NFC seeds 1-7 and NFC 8-16.\n\n"
                    "**2. Record playoff wins:** `/setplayoffwinner season round winner conference`\n"
                    "Record each playoff round winner.\n\n"
                    "**3. Generate payments:** `/generatepayments season`\n"
                    "Creates all payment obligations.\n\n"
                    "**4. Post to channels:** `/postpayments season`\n"
                    "Sends payment summaries to division channels.\n\n"
                    "**Clear data:** `/clearpayments season confirm`\n"
                    "**Clear playoff results:** `/clearplayoffresults season confirm`"
                ),
                inline=False
            )
            
            admin_embed.add_field(
                name="🎰 Wager Management",
                value=(
                    "**Settle wager:** `/settlewager wager_id winning_team`\n"
                    "**Force check all:** `/forcecheckwagers`\n"
                    "**Test parsing:** `/parsescore message_content`"
                ),
                inline=False
            )
            
            admin_embed.add_field(
                name="👥 User Management",
                value=(
                    "**Register user:** `/registeruser user`\n"
                    "**Bulk register:** `/bulkregister users`\n"
                    "**View registered:** `/whoregistered`\n"
                    "**Setup team roles:** `/setuproles`\n"
                    "**Sync helmet:** `/synchelmet member`\n"
                    "**Sync all helmets:** `/syncallhelmets`"
                ),
                inline=False
            )
            
            admin_embed.add_field(
                name="💵 Payment Management",
                value=(
                    "**Create payment:** `/createpayment payer payee amount reason`\n"
                    "**Clear payment:** `/clearpayment payment_id`"
                ),
                inline=False
            )
            
            admin_embed.add_field(
                name="🔄 Other Admin",
                value=(
                    "**Reset whiner stats:** `/resetwhiner [user]`\n"
                    "**Create finances channel:** `/createfinances`"
                ),
                inline=False
            )
            
            await channel.send(embed=admin_embed)
            embeds_posted += 1
            
            # =====================
            # MYMADDEN REFERENCE
            # =====================
            mymadden_embed = discord.Embed(
                title="🏈 MyMadden Integration",
                description="How the bot integrates with MyMadden for automatic features.",
                color=discord.Color.dark_green()
            )
            
            mymadden_embed.add_field(
                name="🔄 Auto-Settlement",
                value=(
                    "When MyMadden bot posts game scores in **#scores**, "
                    "Mistress LIV Bot automatically:\n\n"
                    "1. Parses the score message\n"
                    "2. Identifies the winning team\n"
                    "3. Finds matching pending wagers\n"
                    "4. Settles wagers and notifies users\n"
                    "5. Cross-references with MyMadden website for verification"
                ),
                inline=False
            )
            
            mymadden_embed.add_field(
                name="📊 Score Format",
                value=(
                    "MyMadden posts scores in this format:\n"
                    "```\n"
                    "LIV on MyMadden\n"
                    "Ravens 11-6-0 35 AT 17 Steelers 11-6-0\n"
                    "@Owner1 AT @Owner2\n"
                    "2027 | Post Season | Divisional\n"
                    "```"
                ),
                inline=False
            )
            
            mymadden_embed.add_field(
                name="🌐 Website Reference",
                value=(
                    "The bot also checks [mymadden.com/lg/liv](https://mymadden.com/lg/liv) "
                    "for game results as an additional verification source.\n\n"
                    "**Manual check:** `/checkscore away_team home_team week`"
                ),
                inline=False
            )
            
            await channel.send(embed=mymadden_embed)
            embeds_posted += 1
            
            # Final confirmation
            await interaction.followup.send(
                f"✅ Posted {embeds_posted} guide sections to {channel.mention}",
                ephemeral=True
            )
            
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ I don't have permission to post in {channel.mention}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error posting guide: {e}")
            await interaction.followup.send(
                f"❌ Error posting guide: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(CommandGuideCog(bot))
