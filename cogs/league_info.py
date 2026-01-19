import discord
from discord import app_commands
from discord.ext import commands


class LeagueInfo(commands.Cog):
    """Cog for displaying league information commands."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="rules", description="View the league rules")
    async def rules(self, interaction: discord.Interaction):
        """Display the league rules."""
        embed = discord.Embed(
            title="📜 Mistress LIV League Rules",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="⏰ Advance",
            value="Daily by 11p est or after all games are accounted for.",
            inline=False
        )
        
        embed.add_field(
            name="💬 Communication",
            value=(
                "• If member does not communicate by 5p est, they are subject to be AP'd.\n"
                "• Checking out, going aloof, etc may result in removal and forfeiture of payouts. Must stay active."
            ),
            inline=False
        )
        
        embed.add_field(
            name="🧑‍💼 Coaches",
            value=(
                "• Must use a Created Coach, unless joined after szn 3.\n"
                "• Cannot fire coaches or coordinators."
            ),
            inline=False
        )
        
        embed.add_field(
            name="📋 Rosters",
            value=(
                "• No Roster Position Changes\n"
                "• Can start a player where accessible in the depth chart, excluding K/P at QB, or QB at WR\n"
                "• Only (1) mentor allowed per position\n"
                "• Cannot add a 71+ to psquad then back to roster to resign them\n"
                "• All player edits must be streamed\n"
                "• No editing Throwing Arms (Right or Left) or Throwing Style\n"
                "• Cannot edit physicals or player ratings\n"
                "• Created player name changes ok but must be real names not nicknames"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 Coaching Abilities",
            value=(
                "• **Camp Counselor is BANNED**\n"
                "• Must show coaching abilities used when streaming prior to entering the game\n"
                "• When rewarded a development upgrade in training, provide a screenshot proving Camp Counselor was not used\n"
                "• If found used, players will be downgraded at commissioner's discretion"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📖 Playbooks",
            value=(
                "• No Custom or Live playbooks\n"
                "• Must show playbook when streaming"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔄 Trades",
            value=(
                "• No trade deadline\n"
                "• Trades are off during the resigning stage\n"
                "• No trading w/ CPU\n"
                "• No trading amongst Mav/Goose partners\n"
                "• Only trade assets on the game - no other form of transaction\n"
                "• Cannot trade draft picks the last szn of the franchise"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📺 Streaming",
            value=(
                "• When streaming a game must post the link in #townsquare, the game channel, & DM the opponent\n"
                "• No pausing once a game begins\n"
                "• Streams must be saved, and/or provided upon request\n"
                "• Home Team streams, if unable, visitor has option, if neither can stream it's a Fair Sim\n"
                "• (1) start per game, must resume if disconnected\n"
                "• Injuries stay on for games that result in a FW/FL scenario"
            ),
            inline=False
        )
        
        embed.set_footer(text="Mistress LIV | Use /dynamics for league settings")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="dynamics", description="View the league dynamics and settings")
    async def dynamics(self, interaction: discord.Interaction):
        """Display the league dynamics and settings."""
        embed = discord.Embed(
            title="⚙️ Mistress LIV League Dynamics",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🏈 League Info",
            value=(
                "**League Name:** Mistress LIV\n"
                "**Type:** CPU slow sims\n"
                "**Duration:** 6 szns\n"
                "**Rosters:** Fantasy Draft\n"
                "**Mode:** All Madden"
            ),
            inline=True
        )
        
        embed.add_field(
            name="⭐ Abilities",
            value=(
                "**SS & XF:** Abilities On\n"
                "**Note:** No changing abilities"
            ),
            inline=True
        )
        
        embed.add_field(
            name="⏱️ Game Settings",
            value=(
                "**Quarters:** 11 min\n"
                "**Accel Clock:** 20\n"
                "**Advance:** Daily\n"
                "**Time:** 11p est or week done"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🏥 Injuries",
            value=(
                "**Practice injury & wear and tear:** OFF\n"
                "**Pre & offszn injuries:** OFF\n"
                "**During szn injuries:** ON"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎚️ Sliders",
            value=(
                "**XP:** 70% of par\n"
                "**Injury:** 20\n"
                "**Fatigue:** 25\n"
                "**Roughing passer:** 25\n"
                "**Roughing kicker:** OFF\n"
                "**Run into kicker:** OFF\n"
                "**Intl grounding:** OFF"
            ),
            inline=True
        )
        
        embed.set_footer(text="Mistress LIV | Use /rules for league rules")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="requirements", description="View the league requirements for members")
    async def requirements(self, interaction: discord.Interaction):
        """Display the league requirements."""
        embed = discord.Embed(
            title="✅ Mistress LIV Requirements",
            description="Make sure you complete these requirements to participate in the league.",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="1️⃣ Twitch Recordings",
            value="Make sure your Twitch recordings are on. Your opponents need to have a method to watch the game if they miss it when you go live.",
            inline=False
        )
        
        embed.add_field(
            name="2️⃣ Remote Play Apps",
            value="Download \"Remote Play\" apps for your console. This will allow you to AP, train, roster adjustments, trades, etc. It is your responsibility to be AP'd for your opponent, it is not a commish's job to prepare you.",
            inline=False
        )
        
        embed.add_field(
            name="3️⃣ Madden Companion App",
            value="Please download the Madden Companion App. This allows you to AP in seconds on the app.",
            inline=False
        )
        
        embed.add_field(
            name="4️⃣ Join MyMadden Site",
            value="Request to join league my maddensite by typing `/register` in #townsquare. A commish will then need to assign your team.",
            inline=False
        )
        
        embed.add_field(
            name="5️⃣ Connect Streaming Services",
            value="Connect your Twitch, YouTube, etc by typing `/connectservice`. Select the service, then type in your link for it.",
            inline=False
        )
        
        embed.set_footer(text="Mistress LIV | Use /rules for league rules")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="payouts", description="View the season payout structure")
    async def payouts(self, interaction: discord.Interaction):
        """Display the season payout structure."""
        embed = discord.Embed(
            title="💰 Mistress LIV Payout Structure (SZN 5+)",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="🏈 League Basics",
            value=(
                "• 32 teams (NFC payers fund pot; AFC free/partnered for easy fill)\n"
                "• All payments P2P (Cash App/Venmo preferred)\n"
                "• Commissioner does not collect payments"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🤝 Same-Seed Ties & AFC Share",
            value=(
                "• Each NFC team is paired with the AFC team that finishes in the same seed position\n"
                "• Pairings apply league-wide: playoff to playoff, non-playoff to non-playoff\n"
                "• The NFC partner handles all wagers/earnings for the paired AFC team\n"
                "• **AFC partner gets 20%** of their team's playoff earnings (paid post-season by NFC partner)\n"
                "• **Pre-playoffs election:** AFC partner can elect to pay $50 to NFC partner → $50 returned first on that team's earnings, then 50/50 split"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🏆 Playoff Pot ($900 Max)",
            value=(
                "Paid by NFC non-playoff seeds 8-16 ($100 each P2P when full)\n\n"
                "**Who Pays Who:**\n"
                "• Seeds 15 & 16 → $50 each to (4) WC/Bye Winners\n"
                "• Seeds 13 & 14 → $100 each to (2) Division Winners\n"
                "• Seeds 11 & 12 → $100 each to (1) Conference Winner\n"
                "• Seeds 8, 9, & 10 → $100 each to (1) Super Bowl Winner\n\n"
                "**Dues are due by week 18 of the following season**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💵 Previous Season Playoff Payouts",
            value=(
                "• **WC/Bye Win Only** = $50 (4 payouts)\n"
                "• **Divisional Win Only** = $100 (2 payouts)\n"
                "• **Conference Win Only** = $200 (1 payout)\n"
                "• **Super Bowl Win** = $300 (1 payout)\n"
                "• Pot Reduces $100 per (Open/CPU) NFC Team"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🤖 Open/CPU NFC Team Reductions",
            value=(
                "CPU/open auto-assigned lowest NFC seeds (16 first, then down). CPU pays $0.\n\n"
                "**Pot reductions (lower rounds first):**\n"
                "• 1 open: WC/Bye earnings → $25 each\n"
                "• 2 open: No WC/Bye earnings\n"
                "• 3 open: No WC/Bye + Divisional → $50 each\n"
                "• 4 open: No WC/Bye or Divisional\n"
                "• Continues upward (e.g., 5 open: No WC/Bye/Div + Conference reduced)"
            ),
            inline=False
        )
        
        embed.set_footer(text="Mistress LIV | Check #tracker for current standings")
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(LeagueInfo(bot))
