"""
Profitability Cog - Comprehensive payment generation, tracking, and franchise profitability
Features:
- Generate season payments based on NFC seeds and playoff results
- Clear/reset season payments
- Track franchise profitability (playoff earnings, wagers, dues)
- Post payment summaries to GM division channels
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
import logging

logger = logging.getLogger('MistressLIV.Profitability')

# Payment structure constants
PLAYOFF_PAYOUTS = {
    'wildcard': 50,      # WC/Bye Win = $50 (4 payouts)
    'divisional': 100,   # Divisional Win = $100 (2 payouts)
    'conference': 200,   # Conference Win = $200 (1 payout)
    'superbowl': 300,    # Super Bowl Win = $300 (1 payout)
}

# NFC Seeds 8-16 pay into the pot
# Payment structure: who pays to whom
NFC_PAYER_STRUCTURE = {
    # Seeds 15-16 pay $50 each to WC/Bye winners (split among 4 winners)
    15: {'round': 'wildcard', 'amount': 100},
    16: {'round': 'wildcard', 'amount': 100},
    # Seeds 13-14 pay $100 each to Divisional winners (split among 2 winners)
    13: {'round': 'divisional', 'amount': 100},
    14: {'round': 'divisional', 'amount': 100},
    # Seeds 11-12 pay $100 each to Conference winner
    11: {'round': 'conference', 'amount': 100},
    12: {'round': 'conference', 'amount': 100},
    # Seeds 8-10 pay $100 each to Super Bowl winner
    8: {'round': 'superbowl', 'amount': 100},
    9: {'round': 'superbowl', 'amount': 100},
    10: {'round': 'superbowl', 'amount': 100},
}

# Division channel mapping
DIVISION_CHANNELS = {
    'AFC East': 'afc-east',
    'AFC North': 'afc-north', 
    'AFC South': 'afc-south',
    'AFC West': 'afc-west',
    'NFC East': 'nfc-east',
    'NFC North': 'nfc-north',
    'NFC South': 'nfc-south',
    'NFC West': 'nfc-west',
}


class ProfitabilityCog(commands.Cog):
    """Cog for payment generation and franchise profitability tracking."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
        
    def get_db_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def _ensure_tables(self):
        """Ensure all required tables exist."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Playoff results table for tracking winners
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS playoff_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER NOT NULL,
                round TEXT NOT NULL,
                winner_discord_id INTEGER NOT NULL,
                winner_team_id TEXT,
                loser_discord_id INTEGER,
                loser_team_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Season standings for NFC seeds
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS season_standings (
                standing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER NOT NULL,
                conference TEXT NOT NULL,
                seed INTEGER NOT NULL,
                team_id TEXT NOT NULL,
                user_discord_id INTEGER,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                UNIQUE(season, conference, seed)
            )
        ''')
        
        # Franchise profitability summary
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS franchise_profitability (
                user_discord_id INTEGER NOT NULL,
                season INTEGER NOT NULL,
                playoff_earnings REAL DEFAULT 0,
                dues_paid REAL DEFAULT 0,
                wager_profit REAL DEFAULT 0,
                net_profit REAL DEFAULT 0,
                PRIMARY KEY (user_discord_id, season)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    @app_commands.command(name="setseeding", description="[Admin] Set NFC/AFC seeding for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        conference="NFC or AFC",
        seed="Seed number (1-16)",
        user="The user who has this seed"
    )
    async def set_seeding(
        self,
        interaction: discord.Interaction,
        season: int,
        conference: str,
        seed: int,
        user: discord.Member
    ):
        """Set a team's seeding for a season."""
        conference = conference.upper()
        if conference not in ['NFC', 'AFC']:
            await interaction.response.send_message("Conference must be NFC or AFC", ephemeral=True)
            return
            
        if seed < 1 or seed > 16:
            await interaction.response.send_message("Seed must be between 1 and 16", ephemeral=True)
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get user's team
        team_id = None
        for role in user.roles:
            if role.name.upper() in ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 
                                     'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
                                     'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
                                     'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS']:
                team_id = role.name.upper()
                break
        
        cursor.execute('''
            INSERT OR REPLACE INTO season_standings 
            (season, conference, seed, team_id, user_discord_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (season, conference, seed, team_id, user.id))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ Set {user.display_name} as {conference} #{seed} seed for Season {season}",
            ephemeral=True
        )
    
    @app_commands.command(name="setplayoffwinner", description="[Admin] Record a playoff round winner")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number",
        round="Playoff round (wildcard, divisional, conference, superbowl)",
        winner="The user who won this round"
    )
    @app_commands.choices(round=[
        app_commands.Choice(name="Wild Card / Bye", value="wildcard"),
        app_commands.Choice(name="Divisional", value="divisional"),
        app_commands.Choice(name="Conference Championship", value="conference"),
        app_commands.Choice(name="Super Bowl", value="superbowl"),
    ])
    async def set_playoff_winner(
        self,
        interaction: discord.Interaction,
        season: int,
        round: str,
        winner: discord.Member
    ):
        """Record a playoff round winner."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get winner's team
        team_id = None
        for role in winner.roles:
            if role.name.upper() in ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 
                                     'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
                                     'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
                                     'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS']:
                team_id = role.name.upper()
                break
        
        cursor.execute('''
            INSERT INTO playoff_results (season, round, winner_discord_id, winner_team_id)
            VALUES (?, ?, ?, ?)
        ''', (season, round, winner.id, team_id))
        
        conn.commit()
        conn.close()
        
        round_names = {
            'wildcard': 'Wild Card/Bye',
            'divisional': 'Divisional Round',
            'conference': 'Conference Championship',
            'superbowl': 'Super Bowl'
        }
        
        await interaction.response.send_message(
            f"✅ Recorded {winner.display_name} as {round_names[round]} winner for Season {season}",
            ephemeral=True
        )
    
    @app_commands.command(name="generatepayments", description="[Admin] Generate all payment obligations for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(season="Season number to generate payments for")
    async def generate_payments(self, interaction: discord.Interaction, season: int):
        """Generate all payment obligations based on NFC seeds and playoff results."""
        await interaction.response.defer(thinking=True)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get NFC standings (seeds 8-16 are payers)
        cursor.execute('''
            SELECT seed, user_discord_id, team_id 
            FROM season_standings 
            WHERE season = ? AND conference = 'NFC' AND seed >= 8
            ORDER BY final_seed
        ''', (season,))
        nfc_payers = cursor.fetchall()
        
        # Get playoff winners by round
        cursor.execute('''
            SELECT round, winner_discord_id, winner_team_id
            FROM playoff_results
            WHERE season = ?
        ''', (season,))
        playoff_results = cursor.fetchall()
        
        # Organize winners by round
        winners_by_round = {
            'wildcard': [],
            'divisional': [],
            'conference': [],
            'superbowl': []
        }
        for result in playoff_results:
            round_name, winner_id, team_id = result
            winners_by_round[round_name].append({'user_id': winner_id, 'team_id': team_id})
        
        # Generate payments
        payments_created = 0
        errors = []
        
        for seed, payer_id, payer_team in nfc_payers:
            if payer_id is None:
                errors.append(f"NFC #{seed} has no user assigned")
                continue
                
            if seed not in NFC_PAYER_STRUCTURE:
                continue
                
            payment_info = NFC_PAYER_STRUCTURE[seed]
            target_round = payment_info['round']
            total_amount = payment_info['amount']
            
            # Get winners for this round
            round_winners = winners_by_round.get(target_round, [])
            
            if not round_winners:
                errors.append(f"No {target_round} winners recorded for Season {season}")
                continue
            
            # Split payment among winners
            amount_per_winner = total_amount / len(round_winners)
            
            for winner in round_winners:
                if winner['user_id'] == payer_id:
                    continue  # Don't pay yourself
                    
                # Create payment record
                cursor.execute('''
                    INSERT INTO payments (season_year, payer_discord_id, payee_discord_id, amount, reason, is_paid)
                    VALUES (?, ?, ?, ?, ?, 0)
                ''', (season, payer_id, winner['user_id'], amount_per_winner, 
                      f"Season {season} - NFC #{seed} to {target_round} winner"))
                payments_created += 1
        
        # Update profitability records
        self._update_profitability(cursor, season)
        
        conn.commit()
        conn.close()
        
        # Build response embed
        embed = discord.Embed(
            title=f"💰 Season {season} Payments Generated",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Summary",
            value=f"**Payments Created:** {payments_created}\n**Errors:** {len(errors)}",
            inline=False
        )
        
        if errors:
            embed.add_field(
                name="⚠️ Issues",
                value="\n".join(errors[:5]) + ("\n*...and more*" if len(errors) > 5 else ""),
                inline=False
            )
        
        embed.add_field(
            name="📋 Next Steps",
            value="Use `/postpayments` to send payment notifications to GM channels\nUse `/dues` to view the full dues tracker",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
    
    def _update_profitability(self, cursor, season):
        """Update profitability records for all users in a season."""
        # Get all users with payments in this season
        cursor.execute('''
            SELECT DISTINCT user_id FROM (
                SELECT payer_discord_id as user_id FROM payments WHERE season_year = ?
                UNION
                SELECT payee_discord_id as user_id FROM payments WHERE season_year = ?
            )
        ''', (season, season))
        users = cursor.fetchall()
        
        for (user_id,) in users:
            # Calculate dues paid (as payer)
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE season_year = ? AND payer_discord_id = ?
            ''', (season, user_id))
            dues_paid = cursor.fetchone()[0]
            
            # Calculate playoff earnings (as payee)
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE season_year = ? AND payee_discord_id = ?
            ''', (season, user_id))
            playoff_earnings = cursor.fetchone()[0]
            
            # Calculate wager profit
            cursor.execute('''
                SELECT 
                    COALESCE(SUM(CASE WHEN winner_user_id = ? THEN amount ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN winner_user_id != ? AND (home_user_id = ? OR away_user_id = ?) THEN amount ELSE 0 END), 0)
                FROM wagers 
                WHERE season_year = ? AND winner_user_id IS NOT NULL
            ''', (user_id, user_id, user_id, user_id, season))
            wager_profit = cursor.fetchone()[0]
            
            # Calculate net profit
            net_profit = playoff_earnings - dues_paid + wager_profit
            
            # Update or insert profitability record
            cursor.execute('''
                INSERT OR REPLACE INTO franchise_profitability 
                (user_discord_id, season, playoff_earnings, dues_paid, wager_profit, net_profit)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, season, playoff_earnings, dues_paid, wager_profit, net_profit))
    
    @app_commands.command(name="clearpayments", description="[Admin] Clear all payments for a season")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season number to clear payments for",
        confirm="Type 'CONFIRM' to proceed"
    )
    async def clear_payments(self, interaction: discord.Interaction, season: int, confirm: str):
        """Clear all payment records for a season."""
        if confirm != "CONFIRM":
            await interaction.response.send_message(
                "⚠️ To clear payments, you must type `CONFIRM` in the confirm field.\n"
                "This action cannot be undone!",
                ephemeral=True
            )
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Count payments to be deleted
        cursor.execute('SELECT COUNT(*) FROM payments WHERE season_year = ?', (season,))
        count = cursor.fetchone()[0]
        
        # Delete payments
        cursor.execute('DELETE FROM payments WHERE season_year = ?', (season,))
        
        # Clear profitability records for this season
        cursor.execute('DELETE FROM franchise_profitability WHERE season = ?', (season,))
        
        # Clear playoff results
        cursor.execute('DELETE FROM playoff_results WHERE season = ?', (season,))
        
        # Clear standings
        cursor.execute('DELETE FROM season_standings WHERE season = ?', (season,))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title=f"🗑️ Season {season} Data Cleared",
            description=f"Deleted **{count}** payment records and all associated season data.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="postpayments", description="[Admin] Post payment summaries to GM division channels")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(season="Season number")
    async def post_payments(self, interaction: discord.Interaction, season: int):
        """Post payment summaries to each GM division channel."""
        await interaction.response.defer(thinking=True)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get all unpaid payments for the season
        cursor.execute('''
            SELECT p.payer_discord_id, p.payee_discord_id, p.amount, p.reason,
                   t.division
            FROM payments p
            LEFT JOIN teams t ON t.user_discord_id = p.payer_discord_id
            WHERE p.season_year = ? AND p.is_paid = 0
            ORDER BY t.division, p.amount DESC
        ''', (season,))
        payments = cursor.fetchall()
        conn.close()
        
        if not payments:
            await interaction.followup.send(f"No unpaid payments found for Season {season}")
            return
        
        # Group payments by division
        payments_by_division = {}
        for payer_id, payee_id, amount, reason, division in payments:
            if division not in payments_by_division:
                payments_by_division[division] = []
            payments_by_division[division].append({
                'payer_id': payer_id,
                'payee_id': payee_id,
                'amount': amount,
                'reason': reason
            })
        
        # Post to each division channel
        channels_posted = 0
        for division, div_payments in payments_by_division.items():
            if division is None:
                continue
                
            # Find the channel
            channel_name = DIVISION_CHANNELS.get(division)
            if not channel_name:
                continue
                
            channel = discord.utils.get(interaction.guild.text_channels, name=channel_name)
            if not channel:
                continue
            
            # Build embed for this division
            embed = discord.Embed(
                title=f"💰 Season {season} Payment Summary - {division}",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            total_owed = sum(p['amount'] for p in div_payments)
            embed.add_field(
                name="📊 Division Total",
                value=f"**${total_owed:.2f}** outstanding",
                inline=False
            )
            
            # List individual payments
            payment_lines = []
            for p in div_payments[:10]:
                payer = interaction.guild.get_member(p['payer_id'])
                payee = interaction.guild.get_member(p['payee_id'])
                payer_name = payer.display_name if payer else "Unknown"
                payee_name = payee.display_name if payee else "Unknown"
                payment_lines.append(f"• {payer_name} → {payee_name}: **${p['amount']:.2f}**")
            
            if payment_lines:
                embed.add_field(
                    name="💳 Payments Due",
                    value="\n".join(payment_lines),
                    inline=False
                )
            
            embed.set_footer(text="Use /markpaid to record payments | /mypayments to view your status")
            
            await channel.send(embed=embed)
            channels_posted += 1
        
        await interaction.followup.send(f"✅ Posted payment summaries to {channels_posted} division channels")
    
    @app_commands.command(name="profitability", description="View franchise profitability rankings")
    @app_commands.describe(season="Season number (leave empty for all-time)")
    async def view_profitability(self, interaction: discord.Interaction, season: Optional[int] = None):
        """Display franchise profitability leaderboard."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        if season:
            # Single season profitability
            cursor.execute('''
                SELECT user_discord_id, playoff_earnings, dues_paid, wager_profit, net_profit
                FROM franchise_profitability
                WHERE season = ?
                ORDER BY net_profit DESC
            ''', (season,))
            title = f"💰 Season {season} Profitability"
        else:
            # All-time profitability
            cursor.execute('''
                SELECT user_discord_id, 
                       SUM(playoff_earnings) as total_earnings,
                       SUM(dues_paid) as total_dues,
                       SUM(wager_profit) as total_wagers,
                       SUM(net_profit) as total_profit
                FROM franchise_profitability
                GROUP BY user_discord_id
                ORDER BY total_profit DESC
            ''')
            title = "💰 All-Time Franchise Profitability"
        
        results = cursor.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title=title,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        if not results:
            embed.description = "*No profitability data recorded yet.*"
        else:
            # Top earners
            top_lines = []
            for i, (user_id, earnings, dues, wagers, net) in enumerate(results[:10], 1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                
                # Emoji for rank
                if i == 1:
                    rank_emoji = "🥇"
                elif i == 2:
                    rank_emoji = "🥈"
                elif i == 3:
                    rank_emoji = "🥉"
                else:
                    rank_emoji = f"{i}."
                
                # Color code profit/loss
                profit_str = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
                top_lines.append(f"{rank_emoji} **{name}**: {profit_str}")
            
            embed.add_field(
                name="🏆 Rankings",
                value="\n".join(top_lines),
                inline=False
            )
            
            # Summary stats
            total_pot = sum(r[2] for r in results)  # Total dues collected
            total_earnings = sum(r[1] for r in results)  # Total earnings distributed
            
            embed.add_field(
                name="📊 League Summary",
                value=f"**Total Pot:** ${total_pot:.2f}\n**Total Distributed:** ${total_earnings:.2f}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="myprofit", description="View your personal profitability breakdown")
    async def my_profit(self, interaction: discord.Interaction):
        """Show user's personal profitability breakdown."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get all seasons for this user
        cursor.execute('''
            SELECT season, playoff_earnings, dues_paid, wager_profit, net_profit
            FROM franchise_profitability
            WHERE user_discord_id = ?
            ORDER BY season DESC
        ''', (interaction.user.id,))
        results = cursor.fetchall()
        
        # Get totals
        cursor.execute('''
            SELECT 
                SUM(playoff_earnings) as total_earnings,
                SUM(dues_paid) as total_dues,
                SUM(wager_profit) as total_wagers,
                SUM(net_profit) as total_profit
            FROM franchise_profitability
            WHERE user_discord_id = ?
        ''', (interaction.user.id,))
        totals = cursor.fetchone()
        conn.close()
        
        embed = discord.Embed(
            title=f"💰 {interaction.user.display_name}'s Profitability",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        if not results or totals[0] is None:
            embed.description = "*No profitability data recorded yet.*"
        else:
            total_earnings, total_dues, total_wagers, total_profit = totals
            
            # All-time summary
            profit_color = "🟢" if total_profit >= 0 else "🔴"
            embed.add_field(
                name="📊 All-Time Summary",
                value=(
                    f"**Playoff Earnings:** ${total_earnings:.2f}\n"
                    f"**Dues Paid:** ${total_dues:.2f}\n"
                    f"**Wager Profit:** ${total_wagers:.2f}\n"
                    f"{profit_color} **Net Profit:** ${total_profit:.2f}"
                ),
                inline=False
            )
            
            # Season breakdown
            if results:
                season_lines = []
                for season, earnings, dues, wagers, net in results[:5]:
                    net_str = f"+${net:.2f}" if net >= 0 else f"-${abs(net):.2f}"
                    season_lines.append(f"**Season {season}:** {net_str}")
                
                embed.add_field(
                    name="📅 Recent Seasons",
                    value="\n".join(season_lines),
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="viewseasondata", description="View all data for a specific season")
    @app_commands.describe(season="Season number to view")
    async def view_season_data(self, interaction: discord.Interaction, season: int):
        """Display comprehensive season data including standings, playoffs, and payments."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get NFC standings
        cursor.execute('''
            SELECT seed, user_discord_id, team_id
            FROM season_standings
            WHERE season = ? AND conference = 'NFC'
            ORDER BY final_seed
        ''', (season,))
        nfc_standings = cursor.fetchall()
        
        # Get AFC standings
        cursor.execute('''
            SELECT seed, user_discord_id, team_id
            FROM season_standings
            WHERE season = ? AND conference = 'AFC'
            ORDER BY final_seed
        ''', (season,))
        afc_standings = cursor.fetchall()
        
        # Get playoff results
        cursor.execute('''
            SELECT round, winner_discord_id, winner_team_id
            FROM playoff_results
            WHERE season = ?
            ORDER BY 
                CASE round 
                    WHEN 'wildcard' THEN 1 
                    WHEN 'divisional' THEN 2 
                    WHEN 'conference' THEN 3 
                    WHEN 'superbowl' THEN 4 
                END
        ''', (season,))
        playoff_results = cursor.fetchall()
        
        # Get payment summary
        cursor.execute('''
            SELECT COUNT(*), SUM(amount), SUM(CASE WHEN is_paid = 1 THEN amount ELSE 0 END)
            FROM payments
            WHERE season_year = ?
        ''', (season,))
        payment_summary = cursor.fetchone()
        conn.close()
        
        embed = discord.Embed(
            title=f"📊 Season {season} Overview",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # NFC Standings (seeds 8-16 are payers)
        if nfc_standings:
            nfc_lines = []
            for seed, user_id, team_id in nfc_standings:
                member = interaction.guild.get_member(user_id) if user_id else None
                name = member.display_name if member else "CPU/Unassigned"
                payer_mark = " 💵" if seed >= 8 else ""
                nfc_lines.append(f"#{seed}: {name} ({team_id or 'N/A'}){payer_mark}")
            embed.add_field(
                name="🏈 NFC Standings",
                value="\n".join(nfc_lines[:8]) or "Not set",
                inline=True
            )
        
        # Playoff Results
        if playoff_results:
            round_names = {
                'wildcard': 'WC/Bye',
                'divisional': 'Divisional',
                'conference': 'Conference',
                'superbowl': 'Super Bowl'
            }
            playoff_lines = []
            for round_name, winner_id, team_id in playoff_results:
                member = interaction.guild.get_member(winner_id) if winner_id else None
                name = member.display_name if member else "Unknown"
                playoff_lines.append(f"**{round_names.get(round_name, round_name)}:** {name}")
            embed.add_field(
                name="🏆 Playoff Winners",
                value="\n".join(playoff_lines) or "Not recorded",
                inline=True
            )
        
        # Payment Summary
        if payment_summary and payment_summary[0]:
            total_payments, total_amount, paid_amount = payment_summary
            paid_amount = paid_amount or 0
            embed.add_field(
                name="💰 Payment Status",
                value=(
                    f"**Total Payments:** {total_payments}\n"
                    f"**Total Amount:** ${total_amount:.2f}\n"
                    f"**Paid:** ${paid_amount:.2f}\n"
                    f"**Outstanding:** ${(total_amount - paid_amount):.2f}"
                ),
                inline=False
            )
        else:
            embed.add_field(
                name="💰 Payment Status",
                value="No payments generated yet",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="autopopulate", description="[Admin] Auto-populate season data from MyMadden")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        season="Season year from MyMadden (e.g., 2025)",
        mymadden_season="The MyMadden season year to pull data from"
    )
    async def auto_populate(self, interaction: discord.Interaction, season: int, mymadden_season: int):
        """
        Auto-populate season standings and playoff results from MyMadden.
        Matches team roles in Discord to determine who owes what.
        """
        await interaction.response.defer(thinking=True)
        
        try:
            # Import the scraper
            import sys
            sys.path.insert(0, '/home/ubuntu/mistress_liv_bot')
            from mymadden_scraper import MyMaddenScraper, get_standings, get_playoff_results
            
            scraper = MyMaddenScraper()
            
            # Get standings from MyMadden
            standings = get_standings(mymadden_season)
            
            # Get playoff results from MyMadden
            playoff_winners = scraper.get_playoff_winners(mymadden_season)
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Build team to Discord user mapping from roles
            team_to_user = {}
            for member in interaction.guild.members:
                for role in member.roles:
                    role_upper = role.name.upper()
                    if role_upper in ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 
                                     'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
                                     'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
                                     'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS']:
                        team_to_user[role_upper] = member.id
            
            standings_added = 0
            playoff_added = 0
            errors = []
            
            # Process NFC standings
            nfc_standings = standings.get('NFC', [])
            for standing in nfc_standings:
                team_abbrev = standing.team_abbrev
                user_id = team_to_user.get(team_abbrev)
                
                if not user_id and standing.seed >= 8:
                    errors.append(f"NFC #{standing.seed} ({team_abbrev}) - No Discord user with team role")
                
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO season_standings 
                        (season, conference, seed, team_id, user_discord_id, wins, losses)
                        VALUES (?, 'NFC', ?, ?, ?, ?, ?)
                    ''', (season, standing.seed, team_abbrev, user_id, standing.wins, standing.losses))
                    standings_added += 1
                except Exception as e:
                    errors.append(f"Error adding NFC #{standing.seed}: {str(e)}")
            
            # Process AFC standings
            afc_standings = standings.get('AFC', [])
            for standing in afc_standings:
                team_abbrev = standing.team_abbrev
                user_id = team_to_user.get(team_abbrev)
                
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO season_standings 
                        (season, conference, seed, team_id, user_discord_id, wins, losses)
                        VALUES (?, 'AFC', ?, ?, ?, ?, ?)
                    ''', (season, standing.seed, team_abbrev, user_id, standing.wins, standing.losses))
                    standings_added += 1
                except Exception as e:
                    errors.append(f"Error adding AFC #{standing.seed}: {str(e)}")
            
            # Process playoff winners
            for round_name, winners in playoff_winners.items():
                for winner_team in winners:
                    user_id = team_to_user.get(winner_team)
                    
                    if not user_id:
                        errors.append(f"{round_name} winner ({winner_team}) - No Discord user with team role")
                        continue
                    
                    try:
                        cursor.execute('''
                            INSERT INTO playoff_results (season, round, winner_discord_id, winner_team_id)
                            VALUES (?, ?, ?, ?)
                        ''', (season, round_name, user_id, winner_team))
                        playoff_added += 1
                    except Exception as e:
                        errors.append(f"Error adding {round_name} winner: {str(e)}")
            
            conn.commit()
            conn.close()
            
            # Build response embed
            embed = discord.Embed(
                title=f"📥 Season {season} Data Imported from MyMadden",
                color=discord.Color.green() if not errors else discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name="📊 Import Summary",
                value=(
                    f"**Standings Added:** {standings_added}\n"
                    f"**Playoff Winners Added:** {playoff_added}\n"
                    f"**Errors/Warnings:** {len(errors)}"
                ),
                inline=False
            )
            
            # Show NFC payers (seeds 8-16)
            payer_lines = []
            for standing in nfc_standings:
                if standing.seed >= 8 and standing.seed <= 16:
                    user_id = team_to_user.get(standing.team_abbrev)
                    if user_id:
                        member = interaction.guild.get_member(user_id)
                        name = member.display_name if member else "Unknown"
                    else:
                        name = "⚠️ No user assigned"
                    payer_lines.append(f"#{standing.seed}: {standing.team_abbrev} - {name}")
            
            if payer_lines:
                embed.add_field(
                    name="💵 NFC Payers (Seeds 8-16)",
                    value="\n".join(payer_lines),
                    inline=False
                )
            
            if errors:
                embed.add_field(
                    name="⚠️ Issues",
                    value="\n".join(errors[:5]) + ("\n*...and more*" if len(errors) > 5 else ""),
                    inline=False
                )
            
            embed.add_field(
                name="📋 Next Steps",
                value=(
                    "1. Review the imported data with `/viewseasondata`\n"
                    "2. Fix any missing team role assignments\n"
                    "3. Run `/generatepayments` to create payment obligations\n"
                    "4. Run `/postpayments` to notify members"
                ),
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in auto_populate: {e}")
            await interaction.followup.send(
                f"❌ Error importing data from MyMadden: {str(e)}\n\n"
                "Make sure the MyMadden scraper is properly configured and the season year is correct.",
                ephemeral=True
            )
    
    @app_commands.command(name="showpayers", description="Show who owes money based on NFC seeds 8-16")
    @app_commands.describe(season="Season number to check")
    async def show_payers(self, interaction: discord.Interaction, season: int):
        """Display who owes money based on NFC seeding."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get NFC seeds 8-16
        cursor.execute('''
            SELECT seed, user_discord_id, team_id, wins, losses
            FROM season_standings
            WHERE season = ? AND conference = 'NFC' AND seed >= 8 AND seed <= 16
            ORDER BY final_seed
        ''', (season,))
        payers = cursor.fetchall()
        
        # Get playoff winners to show who they pay
        cursor.execute('''
            SELECT round, winner_discord_id, winner_team_id
            FROM playoff_results
            WHERE season = ?
        ''', (season,))
        winners = cursor.fetchall()
        conn.close()
        
        # Organize winners by round
        winners_by_round = {}
        for round_name, winner_id, team_id in winners:
            if round_name not in winners_by_round:
                winners_by_round[round_name] = []
            member = interaction.guild.get_member(winner_id) if winner_id else None
            winners_by_round[round_name].append(member.display_name if member else team_id or "Unknown")
        
        embed = discord.Embed(
            title=f"💵 Season {season} - Who Owes What",
            description="Based on NFC final standings (seeds 8-16 pay into the pot)",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        if not payers:
            embed.add_field(
                name="⚠️ No Data",
                value="No NFC standings data found for this season.\nUse `/autopopulate` or `/setseeding` to add data.",
                inline=False
            )
        else:
            # Group by payment target
            sb_payers = []  # Seeds 8-10 pay SB winner
            conf_payers = []  # Seeds 11-12 pay Conference winner
            div_payers = []  # Seeds 13-14 pay Divisional winners
            wc_payers = []  # Seeds 15-16 pay WC/Bye winners
            
            for seed, user_id, team_id, wins, losses in payers:
                member = interaction.guild.get_member(user_id) if user_id else None
                name = member.display_name if member else f"⚠️ {team_id or 'Unassigned'}"
                record = f"({wins}-{losses})" if wins or losses else ""
                entry = f"#{seed} {name} {record}"
                
                if seed in [8, 9, 10]:
                    sb_payers.append(entry)
                elif seed in [11, 12]:
                    conf_payers.append(entry)
                elif seed in [13, 14]:
                    div_payers.append(entry)
                elif seed in [15, 16]:
                    wc_payers.append(entry)
            
            # Super Bowl payers
            sb_winners = winners_by_round.get('superbowl', ['Not recorded'])
            embed.add_field(
                name=f"🏆 Pay Super Bowl Winner ($100 each)",
                value=f"**Winners:** {', '.join(sb_winners)}\n**Payers:** " + "\n".join(sb_payers),
                inline=False
            )
            
            # Conference payers
            conf_winners = winners_by_round.get('conference', ['Not recorded'])
            embed.add_field(
                name=f"🏈 Pay Conference Winner ($100 each)",
                value=f"**Winners:** {', '.join(conf_winners)}\n**Payers:** " + "\n".join(conf_payers),
                inline=False
            )
            
            # Divisional payers
            div_winners = winners_by_round.get('divisional', ['Not recorded'])
            embed.add_field(
                name=f"📋 Pay Divisional Winners ($100 each)",
                value=f"**Winners:** {', '.join(div_winners)}\n**Payers:** " + "\n".join(div_payers),
                inline=False
            )
            
            # WC/Bye payers
            wc_winners = winners_by_round.get('wildcard', ['Not recorded'])
            embed.add_field(
                name=f"🎯 Pay WC/Bye Winners ($100 split)",
                value=f"**Winners:** {', '.join(wc_winners)}\n**Payers:** " + "\n".join(wc_payers),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="testpayments", description="[Admin] Test view of payment data by team names")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(season="Season year to view (e.g., 2025)")
    async def test_payments(self, interaction: discord.Interaction, season: int):
        """View payment data using team names instead of Discord users - for testing."""
        await interaction.response.defer(ephemeral=True)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get NFC standings with team info
        cursor.execute('''
            SELECT final_seed, team_id, wins, losses
            FROM season_results
            WHERE season_year = ? AND conference = 'NFC'
            ORDER BY final_seed
        ''', (season,))
        nfc_standings = cursor.fetchall()
        
        # Get playoff results with team info (no scores in this schema)
        cursor.execute('''
            SELECT round, winner_team_id, loser_team_id
            FROM playoff_results
            WHERE season = ?
            ORDER BY CASE round
                WHEN 'wildcard' THEN 1
                WHEN 'divisional' THEN 2
                WHEN 'conference' THEN 3
                WHEN 'superbowl' THEN 4
            END
        ''', (season,))
        playoff_results = cursor.fetchall()
        
        # Get payments with team info
        cursor.execute('''
            SELECT p.payment_id, 
                   (SELECT team_id FROM season_results WHERE user_discord_id = p.payer_discord_id AND season_year = ? LIMIT 1) as payer_team,
                   (SELECT team_id FROM season_results WHERE user_discord_id = p.payee_discord_id AND season_year = ? LIMIT 1) as payee_team,
                   p.amount, p.reason, p.is_paid
            FROM payments p
            WHERE p.season_year = ?
            ORDER BY p.payment_id
        ''', (season, season, season))
        payments = cursor.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title=f"🧪 Season {season} Test Data View",
            description="Showing raw data by team names (test mode)",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        # NFC Standings
        if nfc_standings:
            nfc_lines = []
            for seed, team, wins, losses in nfc_standings:
                payer_mark = " 💵" if seed >= 8 else ""
                nfc_lines.append(f"#{seed}: {team} ({wins}-{losses}){payer_mark}")
            embed.add_field(
                name="🏈 NFC Standings (💵 = Payer)",
                value="\n".join(nfc_lines[:16]) or "No data",
                inline=False
            )
        
        # Playoff Results
        if playoff_results:
            round_names = {'wildcard': 'WC', 'divisional': 'DIV', 'conference': 'CONF', 'superbowl': 'SB'}
            playoff_lines = []
            for round_name, winner_team, loser_team in playoff_results:
                playoff_lines.append(f"**{round_names.get(round_name, round_name)}:** {winner_team} def. {loser_team}")
            embed.add_field(
                name="🏆 Playoff Results",
                value="\n".join(playoff_lines) or "No data",
                inline=False
            )
        
        # Payments
        if payments:
            payment_lines = []
            for pid, payer_team, payee_team, amount, desc, is_paid in payments:  # Show all payments
                status = "✅" if is_paid else "⏳"
                payment_lines.append(f"{status} {payer_team or 'Unknown'} → {payee_team or 'Unknown'}: ${amount:.0f}")
            total_payments = len(payments)
            total_amount = sum(p[3] for p in payments)
            paid_amount = sum(p[3] for p in payments if p[5])
            embed.add_field(
                name=f"💰 Payments ({total_payments} total, ${total_amount:.0f} owed, ${paid_amount:.0f} paid)",
                value="\n".join(payment_lines) or "No payments",
                inline=False
            )
        else:
            embed.add_field(name="💰 Payments", value="No payments generated", inline=False)
        
        # Find the finances channel and send there
        finances_channel = discord.utils.get(interaction.guild.text_channels, name='finances')
        if finances_channel:
            await finances_channel.send(embed=embed)
            await interaction.followup.send(f"✅ Season {season} payment data posted to {finances_channel.mention}", ephemeral=True)
        else:
            await interaction.followup.send(embed=embed)


async def setup(bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(ProfitabilityCog(bot))
