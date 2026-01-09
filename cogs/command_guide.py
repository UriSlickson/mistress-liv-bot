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
            # 1. ADMIN COMMANDS (moved to first)
            # =====================
            admin_embed = discord.Embed(
                title="🔧 Admin Commands",
                description="Commands for league administrators only.",
                color=discord.Color.red()
            )
            
            admin_embed.add_field(
                name="📢 Announcements",
                value=(
                    "**Channels only:** `/announce message`\n"
                    "Posts to #townsquare & #announcements\n\n"
                    "**Channels + DM all:** `/announceall message`\n"
                    "Posts to channels AND DMs every member\n\n"
                    "**DM only:** `/dmowners message`\n"
                    "**Post guide:** `/postguide channel`"
                ),
                inline=False
            )
            
            admin_embed.add_field(
                name="🗑️ Channel Management",
                value=(
                    "**Clear a channel:** `/clearchannel confirm:CONFIRM channel:#channel`\n"
                    "Deletes ALL messages in a channel to start fresh.\n"
                    "Must type `CONFIRM` to prevent accidental deletion.\n\n"
                    "*Example: `/clearchannel confirm:CONFIRM channel:#otb`*"
                ),
                inline=False
            )
            
            admin_embed.add_field(
                name="💰 Season End Setup - Step by Step",
                value=(
                    "**STEP 1: Import Seedings (after Super Bowl)**\n"
                    "Use `/bulkseeding` to set all seeds at once:\n"
                    "`/bulkseeding 2027 AFC NE,PIT,CAR,NYG,LAR,BUF,JAX,DEN,...`\n"
                    "`/bulkseeding 2027 NFC LV,ATL,TEN,MIA,SEA,DAL,PHI,IND,...`\n\n"
                    "**STEP 2: Record Playoff Winners**\n"
                    "`/setplayoffwinner 2027 wildcard @user AFC`\n"
                    "`/setplayoffwinner 2027 divisional @user NFC`\n"
                    "...repeat for each round winner\n\n"
                    "**STEP 3: Generate & Post Payments**\n"
                    "`/generatepayments 2027`\n"
                    "`/postpayments 2027`"
                ),
                inline=False
            )
            
            admin_embed.add_field(
                name="📊 Seeding Helper Commands",
                value=(
                    "**Scan team roles:** `/scanteams`\n"
                    "Shows which users have which team roles.\n\n"
                    "**View seedings:** `/viewseedings season`\n"
                    "Check current seedings for a season.\n\n"
                    "**Individual seeding:** `/setseeding season conference seed user`\n"
                    "Set one seed at a time if needed.\n\n"
                    "**Clear data:** `/clearpayments season confirm`"
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
            # 2. MYMADDEN BOT COMMANDS (Part 1)
            # =====================
            mymadden_embed1 = discord.Embed(
                title="🏈 MyMadden Bot Commands",
                description=(
                    "Commands for the **MyMadden Bot** to access league information.\n"
                    "Use `/` prefix for all commands.\n\n"
                    "*Full documentation: [mymadden.com/bot-commands](https://mymadden.com/bot-commands)*"
                ),
                color=discord.Color.dark_green()
            )
            
            mymadden_embed1.add_field(
                name="⭐ MOST IMPORTANT COMMANDS",
                value=(
                    "**`/sync info`** - Sync league info from console\n"
                    "**`/sync rosters`** - Sync team rosters from console\n"
                    "**`/sync stats`** - Sync player stats from console\n\n"
                    "**`/players`** - Post players to #otb channel\n\n"
                    "**`/game-channel create`** - Create a game channel\n"
                    "**`/game-channel clear`** - Clear a game channel"
                ),
                inline=False
            )
            
            mymadden_embed1.add_field(
                name="📋 League Info Commands",
                value=(
                    "`/web` - Link to league website\n"
                    "`/schedule` - Link to league schedule\n"
                    "`/standings` - Link to league standings\n"
                    "`/stats` - Link to league stats\n"
                    "`/trades` - Link to league trades\n"
                    "`/injuries` - Link to injuries table\n"
                    "`/teams` - Link to all teams\n"
                    "`/week` - Current year, stage, and week"
                ),
                inline=False
            )
            
            mymadden_embed1.add_field(
                name="🏟️ Team Commands",
                value=(
                    "`/team {team}` - Link to specified team page\n"
                    "`/owner {team}` - Shows team owner info\n\n"
                    "*{team} can be city, nickname, or abbreviation*\n"
                    "*Example: `/team KC` or `/team Chiefs` or `/team Kansas City`*"
                ),
                inline=False
            )
            
            mymadden_embed1.add_field(
                name="🎮 Game Commands",
                value=(
                    "`/games` - All games for current week\n"
                    "`/unplayed` - Unplayed games this week\n"
                    "`/played` - Played games this week\n"
                    "`/tws {team} [week]` - Team's game for a specific week\n\n"
                    "*tws = Team Week Score*\n"
                    "*Example: `/tws Ravens 15` shows Ravens Week 15 game*"
                ),
                inline=False
            )
            
            await channel.send(embed=mymadden_embed1)
            embeds_posted += 1
            
            # =====================
            # 3. MYMADDEN COMMANDS PART 2
            # =====================
            mymadden_embed2 = discord.Embed(
                title="🏈 MyMadden Bot Commands (Continued)",
                description="Player search, trade block, and social commands.",
                color=discord.Color.dark_green()
            )
            
            mymadden_embed2.add_field(
                name="🔍 Player Search",
                value=(
                    "`/ps [args]` - Search for players\n\n"
                    "**Args can include:**\n"
                    "• Team name/abbreviation\n"
                    "• Player name (first, last, or both)\n"
                    "• `rookie` or `r` for rookies only\n"
                    "• Position or position group\n\n"
                    "**Position Groups:**\n"
                    "• `SKILL` → HB, TE, WR\n"
                    "• `OL` → LT, LG, C, RG, RT\n"
                    "• `DL` → LE, DT, RE\n"
                    "• `LB` → LOLB, MLB, ROLB\n"
                    "• `DB` → CB, FS, SS\n\n"
                    "*Example: `/ps Ravens QB` or `/ps rookie WR`*"
                ),
                inline=False
            )
            
            mymadden_embed2.add_field(
                name="📦 Trade Block",
                value=(
                    "`/tblock [args]` - Search trade block\n\n"
                    "Uses same args as player search.\n"
                    "If one team specified, includes link to their block.\n\n"
                    "*Example: `/tblock Chiefs WR` or `/tblock rookie`*"
                ),
                inline=False
            )
            
            mymadden_embed2.add_field(
                name="👤 Social Commands",
                value=(
                    "*Requires connecting profile on MyMadden*\n\n"
                    "`/whois me` or `/whois @user` - MyMadden profile info\n"
                    "`/twitch me` or `/twitch @user` - Twitch link\n"
                    "`/youtube me` or `/youtube @user` - YouTube link\n"
                    "`/psn me` or `/psn @user` - PSN username\n"
                    "`/xbox me` or `/xbox @user` - Xbox username\n"
                    "`/twitter me` or `/twitter @user` - Twitter link"
                ),
                inline=False
            )
            
            mymadden_embed2.add_field(
                name="🔄 Sync & Other",
                value=(
                    "`/sync` - Trigger data sync from console\n"
                    "`/blog [number]` - Recent blog posts (default 5)\n"
                    "`/help` - Link to bot commands help page\n"
                    "`/hello` - Test command (posts 'Hello, World!')"
                ),
                inline=False
            )
            
            await channel.send(embed=mymadden_embed2)
            embeds_posted += 1
            
            # =====================
            # 4. WAGERS SECTION
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
            # 5. SEASON END PAYOUTS
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
                name="📝 ADMIN: How to Process Season End Payouts",
                value=(
                    "**STEP 1: Set Seedings After Playoffs**\n"
                    "Go to MyMadden standings page and get final seeds.\n"
                    "Run for each conference:\n"
                    "`/bulkseeding 2027 AFC NE,PIT,CAR,NYG,LAR,BUF,JAX,DEN,WAS,LAC,KC,HOU,CHI,ARI,CIN,SF`\n"
                    "`/bulkseeding 2027 NFC LV,ATL,TEN,MIA,SEA,DAL,PHI,IND,GB,NO,TB,MIN,CLE,DET,NYJ,BAL`\n"
                    "*(List teams in order from seed 1-16)*\n\n"
                    "**STEP 2: Record Playoff Winners**\n"
                    "For each playoff round winner, run:\n"
                    "`/setplayoffwinner 2027 wildcard @winner AFC`\n"
                    "`/setplayoffwinner 2027 divisional @winner NFC`\n"
                    "`/setplayoffwinner 2027 conference @winner AFC`\n"
                    "`/setplayoffwinner 2027 superbowl @winner`\n\n"
                    "**STEP 3: Generate Payments**\n"
                    "`/generatepayments 2027`\n\n"
                    "**STEP 4: Post to Division Channels**\n"
                    "`/postpayments 2027`"
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
            # 6. PROFITABILITY (moved above registration)
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
            # 7. REGISTRATION
            # =====================
            reg_embed = discord.Embed(
                title="📝 Registration",
                description="Register as a team owner to receive announcements and get your helmet emoji.",
                color=discord.Color.teal()
            )
            
            reg_embed.add_field(
                name="✨ Automatic Registration",
                value=(
                    "**When an admin assigns you a team role, you are automatically registered!**\n\n"
                    "You'll receive:\n"
                    "• A welcome DM confirming your team\n"
                    "• Your team's helmet emoji added to your name\n"
                    "• League announcements via DM\n\n"
                    "*No action needed - it's all automatic!*"
                ),
                inline=False
            )
            
            reg_embed.add_field(
                name="🏈 Manual Registration",
                value=(
                    "**Command:** `/register`\n\n"
                    "If you already have a team role but weren't auto-registered, "
                    "run this command to register yourself."
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
            # 8. PAYMENTS & DUES
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
            # 9. FUN COMMANDS
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
            # 10. INFO COMMANDS
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
            # 11. MYMADDEN INTEGRATION
            # =====================
            integration_embed = discord.Embed(
                title="🔗 MyMadden + Mistress LIV Integration",
                description="How the two bots work together for automatic features.",
                color=discord.Color.dark_teal()
            )
            
            integration_embed.add_field(
                name="🔄 Auto-Settlement",
                value=(
                    "When MyMadden bot posts game scores in **#scores**, "
                    "Mistress LIV Bot automatically:\n\n"
                    "1. Parses the score message\n"
                    "2. Identifies the winning team\n"
                    "3. Finds matching pending wagers\n"
                    "4. Settles wagers and notifies users\n"
                    "5. Cross-references with MyMadden website"
                ),
                inline=False
            )
            
            integration_embed.add_field(
                name="📊 Score Format Recognized",
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
            
            integration_embed.add_field(
                name="🌐 Website Verification",
                value=(
                    "Mistress LIV Bot also checks [mymadden.com/lg/liv](https://mymadden.com/lg/liv) "
                    "for game results as an additional verification source.\n\n"
                    "**Manual check:** `/checkscore away_team home_team week`"
                ),
                inline=False
            )
            
            await channel.send(embed=integration_embed)
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
