"""
Wagers Cog - Complete wager system for Mistress LIV Bot
Handles creating, tracking, and settling wagers between league members.
"""
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger('MistressLIV.Wagers')


class WagersCog(commands.Cog):
    """Cog for managing wagers between league members."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
    
    def get_user_team(self, guild, user_id):
        """Get the team abbreviation for a user based on their Discord role."""
        member = guild.get_member(user_id)
        if not member:
            return None
        
        # NFL team abbreviations
        nfl_teams = ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 
                     'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC', 
                     'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG', 
                     'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS']
        
        # Team name mappings
        team_names = {
            'Cardinals': 'ARI', 'Falcons': 'ATL', 'Ravens': 'BAL', 'Bills': 'BUF',
            'Panthers': 'CAR', 'Bears': 'CHI', 'Bengals': 'CIN', 'Browns': 'CLE',
            'Cowboys': 'DAL', 'Broncos': 'DEN', 'Lions': 'DET', 'Packers': 'GB',
            'Texans': 'HOU', 'Colts': 'IND', 'Jaguars': 'JAX', 'Chiefs': 'KC',
            'Chargers': 'LAC', 'Rams': 'LAR', 'Raiders': 'LV', 'Dolphins': 'MIA',
            'Vikings': 'MIN', 'Patriots': 'NE', 'Saints': 'NO', 'Giants': 'NYG',
            'Jets': 'NYJ', 'Eagles': 'PHI', 'Steelers': 'PIT', 'Seahawks': 'SEA',
            '49ers': 'SF', 'Buccaneers': 'TB', 'Titans': 'TEN', 'Commanders': 'WAS'
        }
        
        for role in member.roles:
            role_name = role.name.upper()
            if role_name in nfl_teams:
                return role_name
            # Check team names
            for name, abbr in team_names.items():
                if name.lower() in role.name.lower():
                    return abbr
        
        return None
    
    @app_commands.command(name="wager", description="Create a wager with another team owner")
    @app_commands.describe(
        opponent="The team owner you want to wager against",
        amount="Amount of the wager in dollars",
        week="Week number (1-18 for regular season, or 19-22 for playoffs)",
        description="Optional description for the wager"
    )
    async def wager(
        self, 
        interaction: discord.Interaction, 
        opponent: discord.Member,
        amount: float,
        week: int,
        description: str = None
    ):
        """Create a wager challenge against another team owner."""
        await interaction.response.defer()
        
        # Validate amount
        if amount <= 0:
            await interaction.followup.send("❌ Wager amount must be greater than $0!", ephemeral=True)
            return
        
        if amount > 100:
            await interaction.followup.send("❌ Maximum wager amount is $100!", ephemeral=True)
            return
        
        # Validate week
        if week < 1 or week > 22:
            await interaction.followup.send("❌ Week must be between 1-18 (regular) or 19-22 (playoffs)!", ephemeral=True)
            return
        
        # Can't wager against yourself
        if opponent.id == interaction.user.id:
            await interaction.followup.send("❌ You can't wager against yourself!", ephemeral=True)
            return
        
        # Can't wager against bots
        if opponent.bot:
            await interaction.followup.send("❌ You can't wager against a bot!", ephemeral=True)
            return
        
        # Get teams for both users
        challenger_team = self.get_user_team(interaction.guild, interaction.user.id)
        opponent_team = self.get_user_team(interaction.guild, opponent.id)
        
        if not challenger_team:
            await interaction.followup.send("❌ You don't have a team role! Please contact an admin.", ephemeral=True)
            return
        
        if not opponent_team:
            await interaction.followup.send(f"❌ {opponent.display_name} doesn't have a team role!", ephemeral=True)
            return
        
        # Determine week type
        week_type = "regular" if week <= 18 else "playoffs"
        
        # Get current season (use current year)
        season_year = datetime.now().year
        
        # Check if wager already exists between these users for this week
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wager_id FROM wagers 
            WHERE season_year = ? AND week = ?
            AND ((home_user_id = ? AND away_user_id = ?) OR (home_user_id = ? AND away_user_id = ?))
            AND winner_user_id IS NULL
        ''', (season_year, week, interaction.user.id, opponent.id, opponent.id, interaction.user.id))
        
        existing = cursor.fetchone()
        if existing:
            conn.close()
            await interaction.followup.send(f"❌ You already have an active wager with {opponent.display_name} for Week {week}!", ephemeral=True)
            return
        
        # Create the wager
        cursor.execute('''
            INSERT INTO wagers (season_year, week, week_type, home_team_id, away_team_id, 
                               home_user_id, away_user_id, amount, home_accepted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', (season_year, week, week_type, challenger_team, opponent_team, 
              interaction.user.id, opponent.id, amount))
        
        wager_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Create embed for the wager challenge
        embed = discord.Embed(
            title="🎰 New Wager Challenge!",
            description=f"{interaction.user.mention} has challenged {opponent.mention} to a wager!",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="💰 Amount", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="📅 Week", value=f"Week {week} ({week_type.title()})", inline=True)
        embed.add_field(name="🆔 Wager ID", value=f"#{wager_id}", inline=True)
        embed.add_field(name="🏈 Matchup", value=f"{challenger_team} vs {opponent_team}", inline=False)
        
        if description:
            embed.add_field(name="📝 Description", value=description, inline=False)
        
        embed.add_field(
            name="⏳ Status", 
            value=f"Waiting for {opponent.mention} to accept!\nUse `/acceptwager {wager_id}` to accept or `/declinewager {wager_id}` to decline.",
            inline=False
        )
        
        embed.set_footer(text=f"Wager created at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        await interaction.followup.send(embed=embed)
        
        # Try to DM the opponent
        try:
            dm_embed = discord.Embed(
                title="🎰 You've Been Challenged to a Wager!",
                description=f"{interaction.user.display_name} wants to wager ${amount:.2f} on Week {week}!",
                color=discord.Color.gold()
            )
            dm_embed.add_field(name="🆔 Wager ID", value=f"#{wager_id}", inline=True)
            dm_embed.add_field(name="🏈 Matchup", value=f"{challenger_team} vs {opponent_team}", inline=True)
            dm_embed.add_field(
                name="📋 Actions",
                value=f"Use `/acceptwager {wager_id}` to accept\nUse `/declinewager {wager_id}` to decline",
                inline=False
            )
            await opponent.send(embed=dm_embed)
        except:
            pass  # DMs might be disabled
    
    @app_commands.command(name="acceptwager", description="Accept a pending wager")
    @app_commands.describe(wager_id="The ID of the wager to accept")
    async def acceptwager(self, interaction: discord.Interaction, wager_id: int):
        """Accept a wager that was sent to you."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the wager
        cursor.execute('''
            SELECT wager_id, season_year, week, home_team_id, away_team_id, 
                   home_user_id, away_user_id, amount, away_accepted, winner_user_id
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        wager_id, season, week, home_team, away_team, home_user, away_user, amount, accepted, winner = wager
        
        # Check if user is the opponent
        if interaction.user.id != away_user:
            conn.close()
            await interaction.followup.send("❌ This wager wasn't sent to you!", ephemeral=True)
            return
        
        # Check if already accepted
        if accepted:
            conn.close()
            await interaction.followup.send("❌ This wager has already been accepted!", ephemeral=True)
            return
        
        # Check if already has a winner
        if winner:
            conn.close()
            await interaction.followup.send("❌ This wager has already been completed!", ephemeral=True)
            return
        
        # Accept the wager
        cursor.execute('UPDATE wagers SET away_accepted = 1 WHERE wager_id = ?', (wager_id,))
        conn.commit()
        conn.close()
        
        # Get challenger mention
        challenger = interaction.guild.get_member(home_user)
        challenger_mention = challenger.mention if challenger else f"User {home_user}"
        
        embed = discord.Embed(
            title="✅ Wager Accepted!",
            description=f"{interaction.user.mention} has accepted the wager from {challenger_mention}!",
            color=discord.Color.green()
        )
        embed.add_field(name="🆔 Wager ID", value=f"#{wager_id}", inline=True)
        embed.add_field(name="💰 Amount", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="📅 Week", value=f"Week {week}", inline=True)
        embed.add_field(name="🏈 Matchup", value=f"{home_team} vs {away_team}", inline=False)
        embed.add_field(
            name="📋 Next Steps",
            value="After the game, the winner should use `/wagerwin` to claim victory!",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="declinewager", description="Decline a pending wager")
    @app_commands.describe(wager_id="The ID of the wager to decline")
    async def declinewager(self, interaction: discord.Interaction, wager_id: int):
        """Decline a wager that was sent to you."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the wager
        cursor.execute('''
            SELECT away_user_id, home_user_id, amount, away_accepted, winner_user_id
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        away_user, home_user, amount, accepted, winner = wager
        
        # Check if user is the opponent or the creator
        if interaction.user.id not in [away_user, home_user]:
            conn.close()
            await interaction.followup.send("❌ This wager doesn't involve you!", ephemeral=True)
            return
        
        # Check if already accepted
        if accepted:
            conn.close()
            await interaction.followup.send("❌ This wager has already been accepted and cannot be declined!", ephemeral=True)
            return
        
        # Delete the wager
        cursor.execute('DELETE FROM wagers WHERE wager_id = ?', (wager_id,))
        conn.commit()
        conn.close()
        
        await interaction.followup.send(f"❌ Wager #{wager_id} has been declined and removed.")
    
    @app_commands.command(name="mywagers", description="View your active wagers")
    async def mywagers(self, interaction: discord.Interaction):
        """View all your active wagers."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all wagers involving this user
        cursor.execute('''
            SELECT wager_id, season_year, week, home_team_id, away_team_id, 
                   home_user_id, away_user_id, amount, home_accepted, away_accepted, 
                   winner_user_id, is_paid
            FROM wagers 
            WHERE (home_user_id = ? OR away_user_id = ?)
            ORDER BY season_year DESC, week DESC
        ''', (interaction.user.id, interaction.user.id))
        
        wagers = cursor.fetchall()
        conn.close()
        
        if not wagers:
            await interaction.followup.send("📭 You don't have any wagers yet! Use `/wager` to create one.", ephemeral=True)
            return
        
        # Separate into categories
        pending = []
        active = []
        completed = []
        
        for w in wagers:
            wager_id, season, week, home_team, away_team, home_user, away_user, amount, home_acc, away_acc, winner, paid = w
            
            # Get opponent info
            opponent_id = away_user if home_user == interaction.user.id else home_user
            opponent = interaction.guild.get_member(opponent_id)
            opponent_name = opponent.display_name if opponent else f"User {opponent_id}"
            
            wager_info = f"**#{wager_id}** - Week {week}: ${amount:.2f} vs {opponent_name}"
            
            if winner:
                status = "✅ Won" if winner == interaction.user.id else "❌ Lost"
                paid_status = " (Paid)" if paid else " (Unpaid)"
                completed.append(f"{wager_info} - {status}{paid_status}")
            elif home_acc and away_acc:
                active.append(f"{wager_info} - 🎮 In Progress")
            else:
                if home_user == interaction.user.id:
                    pending.append(f"{wager_info} - ⏳ Waiting for acceptance")
                else:
                    pending.append(f"{wager_info} - 📩 Needs your response")
        
        embed = discord.Embed(
            title=f"🎰 {interaction.user.display_name}'s Wagers",
            color=discord.Color.gold()
        )
        
        if pending:
            embed.add_field(name="⏳ Pending", value="\n".join(pending[:5]) or "None", inline=False)
        
        if active:
            embed.add_field(name="🎮 Active", value="\n".join(active[:5]) or "None", inline=False)
        
        if completed:
            embed.add_field(name="✅ Completed", value="\n".join(completed[:5]) or "None", inline=False)
        
        # Calculate stats
        wins = sum(1 for w in wagers if w[10] == interaction.user.id)
        losses = sum(1 for w in wagers if w[10] and w[10] != interaction.user.id)
        total_won = sum(w[7] for w in wagers if w[10] == interaction.user.id)
        total_lost = sum(w[7] for w in wagers if w[10] and w[10] != interaction.user.id)
        
        embed.add_field(
            name="📊 Stats",
            value=f"Record: **{wins}-{losses}**\nNet: **${total_won - total_lost:+.2f}**",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="wagerwin", description="Claim victory on a wager after winning the game")
    @app_commands.describe(wager_id="The ID of the wager you won")
    async def wagerwin(self, interaction: discord.Interaction, wager_id: int):
        """Claim victory on a wager."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the wager
        cursor.execute('''
            SELECT wager_id, week, home_team_id, away_team_id, 
                   home_user_id, away_user_id, amount, home_accepted, away_accepted, winner_user_id
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        wager_id, week, home_team, away_team, home_user, away_user, amount, home_acc, away_acc, winner = wager
        
        # Check if user is involved
        if interaction.user.id not in [home_user, away_user]:
            conn.close()
            await interaction.followup.send("❌ This wager doesn't involve you!", ephemeral=True)
            return
        
        # Check if wager was accepted
        if not (home_acc and away_acc):
            conn.close()
            await interaction.followup.send("❌ This wager hasn't been accepted yet!", ephemeral=True)
            return
        
        # Check if already has a winner
        if winner:
            conn.close()
            await interaction.followup.send("❌ This wager already has a winner!", ephemeral=True)
            return
        
        # Get the opponent
        opponent_id = away_user if home_user == interaction.user.id else home_user
        opponent = interaction.guild.get_member(opponent_id)
        opponent_mention = opponent.mention if opponent else f"<@{opponent_id}>"
        
        # Get winner's team
        winner_team = home_team if home_user == interaction.user.id else away_team
        
        # Set the winner
        cursor.execute('''
            UPDATE wagers SET winner_team_id = ?, winner_user_id = ? WHERE wager_id = ?
        ''', (winner_team, interaction.user.id, wager_id))
        
        # Update franchise stats
        cursor.execute('''
            UPDATE franchise_stats SET total_wager_wins = total_wager_wins + ? 
            WHERE user_discord_id = ?
        ''', (amount, interaction.user.id))
        
        cursor.execute('''
            UPDATE franchise_stats SET total_wager_losses = total_wager_losses + ? 
            WHERE user_discord_id = ?
        ''', (amount, opponent_id))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🏆 Wager Victory Claimed!",
            description=f"{interaction.user.mention} claims victory over {opponent_mention}!",
            color=discord.Color.green()
        )
        embed.add_field(name="🆔 Wager ID", value=f"#{wager_id}", inline=True)
        embed.add_field(name="💰 Amount", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="📅 Week", value=f"Week {week}", inline=True)
        embed.add_field(
            name="💸 Payment",
            value=f"{opponent_mention} owes {interaction.user.mention} **${amount:.2f}**\nUse `/markwagerpaid {wager_id}` once paid!",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="markwagerpaid", description="Mark a wager as paid")
    @app_commands.describe(wager_id="The ID of the wager to mark as paid")
    async def markwagerpaid(self, interaction: discord.Interaction, wager_id: int):
        """Mark a wager as paid (winner confirms receipt)."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the wager
        cursor.execute('''
            SELECT winner_user_id, home_user_id, away_user_id, amount, is_paid
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        winner, home_user, away_user, amount, is_paid = wager
        
        # Check if wager has a winner
        if not winner:
            conn.close()
            await interaction.followup.send("❌ This wager doesn't have a winner yet!", ephemeral=True)
            return
        
        # Only winner or admin can mark as paid
        is_admin = interaction.user.guild_permissions.administrator
        if interaction.user.id != winner and not is_admin:
            conn.close()
            await interaction.followup.send("❌ Only the winner can mark this wager as paid!", ephemeral=True)
            return
        
        # Check if already paid
        if is_paid:
            conn.close()
            await interaction.followup.send("❌ This wager is already marked as paid!", ephemeral=True)
            return
        
        # Mark as paid
        cursor.execute('UPDATE wagers SET is_paid = 1 WHERE wager_id = ?', (wager_id,))
        conn.commit()
        conn.close()
        
        # Get loser info
        loser_id = away_user if winner == home_user else home_user
        loser = interaction.guild.get_member(loser_id)
        loser_mention = loser.mention if loser else f"<@{loser_id}>"
        
        embed = discord.Embed(
            title="💰 Wager Paid!",
            description=f"Wager #{wager_id} has been marked as paid!",
            color=discord.Color.green()
        )
        embed.add_field(name="💵 Amount", value=f"${amount:.2f}", inline=True)
        embed.add_field(name="👤 Paid by", value=loser_mention, inline=True)
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="wagerboard", description="View the wager leaderboard")
    async def wagerboard(self, interaction: discord.Interaction):
        """View the wager leaderboard showing top winners and losers."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all completed wagers
        cursor.execute('''
            SELECT home_user_id, away_user_id, amount, winner_user_id
            FROM wagers WHERE winner_user_id IS NOT NULL
        ''')
        
        wagers = cursor.fetchall()
        conn.close()
        
        if not wagers:
            await interaction.followup.send("📭 No completed wagers yet! Be the first to create one with `/wager`.")
            return
        
        # Calculate stats for each user
        user_stats = {}
        
        for home_user, away_user, amount, winner in wagers:
            # Initialize users if not exists
            for user_id in [home_user, away_user]:
                if user_id not in user_stats:
                    user_stats[user_id] = {'wins': 0, 'losses': 0, 'won': 0.0, 'lost': 0.0}
            
            # Update stats
            loser = away_user if winner == home_user else home_user
            user_stats[winner]['wins'] += 1
            user_stats[winner]['won'] += amount
            user_stats[loser]['losses'] += 1
            user_stats[loser]['lost'] += amount
        
        # Sort by net earnings
        sorted_users = sorted(
            user_stats.items(),
            key=lambda x: x[1]['won'] - x[1]['lost'],
            reverse=True
        )
        
        embed = discord.Embed(
            title="🎰 Wager Leaderboard",
            description="Top performers in head-to-head wagers",
            color=discord.Color.gold()
        )
        
        # Top earners
        top_earners = []
        for i, (user_id, stats) in enumerate(sorted_users[:5], 1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            net = stats['won'] - stats['lost']
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            top_earners.append(f"{medal} **{name}**: {stats['wins']}-{stats['losses']} (${net:+.2f})")
        
        embed.add_field(name="🏆 Top Earners", value="\n".join(top_earners) or "No data", inline=False)
        
        # Biggest losers (bottom of the list)
        bottom_users = sorted_users[-5:][::-1]
        biggest_losers = []
        for i, (user_id, stats) in enumerate(bottom_users, 1):
            if stats['won'] - stats['lost'] < 0:  # Only show if actually losing
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                net = stats['won'] - stats['lost']
                biggest_losers.append(f"{i}. **{name}**: {stats['wins']}-{stats['losses']} (${net:+.2f})")
        
        if biggest_losers:
            embed.add_field(name="📉 Biggest Losers", value="\n".join(biggest_losers), inline=False)
        
        # Total stats
        total_wagers = len(wagers)
        total_money = sum(w[2] for w in wagers)
        embed.add_field(
            name="📊 Overall Stats",
            value=f"Total Wagers: **{total_wagers}**\nTotal Money Wagered: **${total_money:.2f}**",
            inline=False
        )
        
        embed.set_footer(text="Use /wager to challenge someone!")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="cancelwager", description="Cancel a wager you created (before it's accepted)")
    @app_commands.describe(wager_id="The ID of the wager to cancel")
    async def cancelwager(self, interaction: discord.Interaction, wager_id: int):
        """Cancel a wager that hasn't been accepted yet."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the wager
        cursor.execute('''
            SELECT home_user_id, away_accepted, winner_user_id
            FROM wagers WHERE wager_id = ?
        ''', (wager_id,))
        
        wager = cursor.fetchone()
        
        if not wager:
            conn.close()
            await interaction.followup.send(f"❌ Wager #{wager_id} not found!", ephemeral=True)
            return
        
        home_user, accepted, winner = wager
        
        # Check if user is the creator
        is_admin = interaction.user.guild_permissions.administrator
        if interaction.user.id != home_user and not is_admin:
            conn.close()
            await interaction.followup.send("❌ Only the wager creator can cancel it!", ephemeral=True)
            return
        
        # Check if already accepted
        if accepted:
            conn.close()
            await interaction.followup.send("❌ This wager has already been accepted and cannot be cancelled!", ephemeral=True)
            return
        
        # Delete the wager
        cursor.execute('DELETE FROM wagers WHERE wager_id = ?', (wager_id,))
        conn.commit()
        conn.close()
        
        await interaction.followup.send(f"✅ Wager #{wager_id} has been cancelled.")


async def setup(bot):
    await bot.add_cog(WagersCog(bot))
