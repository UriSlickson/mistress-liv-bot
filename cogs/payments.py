"""
Payments Cog - User-facing payment tracking and management
Features:
- View who owes you money
- View who you owe money to
- View payment schedule in #dues
- Mark payments as paid
- Create manual payments
- Top earners/losers leaderboards
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime
from typing import Optional, List
import logging

logger = logging.getLogger('MistressLIV.Payments')


class PaymentsCog(commands.Cog):
    """Cog for user-facing payment tracking and management."""
    
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
        
        # Manual payments table for tracking individual debts
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS manual_payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                season INTEGER,
                debtor_id INTEGER NOT NULL,
                creditor_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                reason TEXT,
                is_paid INTEGER DEFAULT 0,
                paid_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _get_user_team(self, member: discord.Member) -> Optional[str]:
        """Get a user's team from their roles."""
        team_roles = ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 
                      'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
                      'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
                      'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS',
                      '49ERS', 'BEARS', 'BENGALS', 'BILLS', 'BRONCOS', 'BROWNS',
                      'BUCCANEERS', 'CARDINALS', 'CHARGERS', 'CHIEFS', 'COLTS',
                      'COMMANDERS', 'COWBOYS', 'DOLPHINS', 'EAGLES', 'FALCONS',
                      'GIANTS', 'JAGUARS', 'JETS', 'LIONS', 'PACKERS', 'PANTHERS',
                      'PATRIOTS', 'RAIDERS', 'RAMS', 'RAVENS', 'SAINTS', 'SEAHAWKS',
                      'STEELERS', 'TEXANS', 'TITANS', 'VIKINGS']
        for role in member.roles:
            if role.name.upper() in team_roles:
                return role.name
        return None

    @app_commands.command(name="whooowesme", description="See who owes you money")
    async def who_owes_me(self, interaction: discord.Interaction):
        """Show all unpaid debts owed TO the user."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get from manual payments
        cursor.execute('''
            SELECT payment_id, debtor_id, amount, reason, created_at
            FROM manual_payments
            WHERE creditor_id = ? AND is_paid = 0
            ORDER BY created_at DESC
        ''', (interaction.user.id,))
        manual_debts = cursor.fetchall()
        
        # Get from generated payments table
        cursor.execute('''
            SELECT payment_id, payer_discord_id, amount, season, round
            FROM payments
            WHERE payee_discord_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        generated_debts = cursor.fetchall()
        
        conn.close()
        
        if not manual_debts and not generated_debts:
            await interaction.response.send_message(
                "💰 **No one owes you money!** You're all squared up.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="💰 Money Owed TO You",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        total_owed = 0
        
        # Manual payments
        if manual_debts:
            debts_text = ""
            for payment_id, debtor_id, amount, reason, created_at in manual_debts:
                debtor = interaction.guild.get_member(debtor_id)
                debtor_name = debtor.display_name if debtor else f"User {debtor_id}"
                reason_text = f" - {reason}" if reason else ""
                debts_text += f"• **{debtor_name}**: ${amount:.2f}{reason_text} (ID: {payment_id})\n"
                total_owed += amount
            embed.add_field(name="📋 Manual Payments", value=debts_text, inline=False)
        
        # Generated payments (from playoff results)
        if generated_debts:
            debts_text = ""
            for payment_id, payer_id, amount, season, round_name in generated_debts:
                payer = interaction.guild.get_member(payer_id)
                payer_name = payer.display_name if payer else f"User {payer_id}"
                debts_text += f"• **{payer_name}**: ${amount:.2f} - Szn {season} {round_name}\n"
                total_owed += amount
            embed.add_field(name="🏆 Playoff Earnings", value=debts_text, inline=False)
        
        embed.add_field(name="💵 Total Owed to You", value=f"**${total_owed:.2f}**", inline=False)
        embed.set_footer(text="Use /markpaid to mark debts as paid")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="whoiowe", description="See who you owe money to")
    async def who_i_owe(self, interaction: discord.Interaction):
        """Show all unpaid debts the user owes."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get from manual payments
        cursor.execute('''
            SELECT payment_id, creditor_id, amount, reason, created_at
            FROM manual_payments
            WHERE debtor_id = ? AND is_paid = 0
            ORDER BY created_at DESC
        ''', (interaction.user.id,))
        manual_debts = cursor.fetchall()
        
        # Get from generated payments table
        cursor.execute('''
            SELECT payment_id, payee_discord_id, amount, season, round
            FROM payments
            WHERE payer_discord_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        generated_debts = cursor.fetchall()
        
        conn.close()
        
        if not manual_debts and not generated_debts:
            await interaction.response.send_message(
                "✅ **You don't owe anyone money!** You're all squared up.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="💸 Money YOU Owe",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        total_owed = 0
        
        # Manual payments
        if manual_debts:
            debts_text = ""
            for payment_id, creditor_id, amount, reason, created_at in manual_debts:
                creditor = interaction.guild.get_member(creditor_id)
                creditor_name = creditor.display_name if creditor else f"User {creditor_id}"
                reason_text = f" - {reason}" if reason else ""
                debts_text += f"• **{creditor_name}**: ${amount:.2f}{reason_text}\n"
                total_owed += amount
            embed.add_field(name="📋 Manual Payments", value=debts_text, inline=False)
        
        # Generated payments (from playoff results)
        if generated_debts:
            debts_text = ""
            for payment_id, recipient_id, amount, season, round_name in generated_debts:
                recipient = interaction.guild.get_member(recipient_id)
                recipient_name = recipient.display_name if recipient else f"User {recipient_id}"
                debts_text += f"• **{recipient_name}**: ${amount:.2f} - Szn {season} {round_name}\n"
                total_owed += amount
            embed.add_field(name="🏆 Playoff Dues", value=debts_text, inline=False)
        
        embed.add_field(name="💵 Total You Owe", value=f"**${total_owed:.2f}**", inline=False)
        embed.set_footer(text="Pay up! 💰")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="mypayments", description="View your complete payment status")
    async def my_payments(self, interaction: discord.Interaction):
        """Show a complete summary of user's payment status."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # What I owe (manual)
        cursor.execute('''
            SELECT SUM(amount) FROM manual_payments
            WHERE debtor_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        manual_owed = cursor.fetchone()[0] or 0
        
        # What I owe (generated)
        cursor.execute('''
            SELECT SUM(amount) FROM payments
            WHERE payer_discord_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        generated_owed = cursor.fetchone()[0] or 0
        
        # What's owed to me (manual)
        cursor.execute('''
            SELECT SUM(amount) FROM manual_payments
            WHERE creditor_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        manual_incoming = cursor.fetchone()[0] or 0
        
        # What's owed to me (generated)
        cursor.execute('''
            SELECT SUM(amount) FROM payments
            WHERE payee_discord_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        generated_incoming = cursor.fetchone()[0] or 0
        
        conn.close()
        
        total_owed = manual_owed + generated_owed
        total_incoming = manual_incoming + generated_incoming
        net = total_incoming - total_owed
        
        embed = discord.Embed(
            title=f"💳 Payment Summary for {interaction.user.display_name}",
            color=discord.Color.green() if net >= 0 else discord.Color.red(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="💸 You Owe", value=f"${total_owed:.2f}", inline=True)
        embed.add_field(name="💰 Owed to You", value=f"${total_incoming:.2f}", inline=True)
        embed.add_field(name="📊 Net Position", value=f"${net:+.2f}", inline=True)
        
        if net > 0:
            embed.set_footer(text="You're in the green! 🎉")
        elif net < 0:
            embed.set_footer(text="Time to pay up! 💸")
        else:
            embed.set_footer(text="All squared up! ✅")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="paymentschedule", description="View all outstanding payments (posts to #payouts)")
    @app_commands.describe(season="Season to view (optional, shows all if not specified)")
    async def payment_schedule(self, interaction: discord.Interaction, season: Optional[int] = None):
        """Post all outstanding payments to the #payouts channel."""
        await interaction.response.defer()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get all unpaid manual payments
        if season:
            cursor.execute('''
                SELECT payment_id, debtor_id, creditor_id, amount, reason, created_at
                FROM manual_payments
                WHERE is_paid = 0 AND season = ?
                ORDER BY created_at
            ''', (season,))
        else:
            cursor.execute('''
                SELECT payment_id, debtor_id, creditor_id, amount, reason, created_at
                FROM manual_payments
                WHERE is_paid = 0
                ORDER BY created_at
            ''')
        manual_payments = cursor.fetchall()
        
        # Get all unpaid generated payments
        if season:
            cursor.execute('''
                SELECT payment_id, payer_discord_id, payee_discord_id, amount, season, round
                FROM payments
                WHERE is_paid = 0 AND season = ?
                ORDER BY season, round
            ''', (season,))
        else:
            cursor.execute('''
                SELECT payment_id, payer_discord_id, payee_discord_id, amount, season, round
                FROM payments
                WHERE is_paid = 0
                ORDER BY season, round
            ''')
        generated_payments = cursor.fetchall()
        
        conn.close()
        
        if not manual_payments and not generated_payments:
            await interaction.followup.send("✅ **No outstanding payments!** Everyone is squared up.")
            return
        
        # Find #payouts channel (or fallback to #dues for backwards compatibility)
        payouts_channel = discord.utils.get(interaction.guild.channels, name='payouts')
        if not payouts_channel:
            payouts_channel = discord.utils.get(interaction.guild.channels, name='dues')
        if not payouts_channel:
            await interaction.followup.send("❌ Could not find #payouts channel! Use `/createpayouts` to create one.", ephemeral=True)
            return
        
        # Build the payment schedule embed
        embed = discord.Embed(
            title=f"📋 Payment Schedule{f' - Season {season}' if season else ''}",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        total_outstanding = 0
        
        # Manual payments section
        if manual_payments:
            payments_text = ""
            for pid, debtor_id, creditor_id, amount, reason, created_at in manual_payments[:15]:
                debtor = interaction.guild.get_member(debtor_id)
                creditor = interaction.guild.get_member(creditor_id)
                debtor_name = debtor.mention if debtor else f"User {debtor_id}"
                creditor_name = creditor.mention if creditor else f"User {creditor_id}"
                reason_text = f" ({reason})" if reason else ""
                payments_text += f"• {debtor_name} → {creditor_name}: **${amount:.2f}**{reason_text}\n"
                total_outstanding += amount
            
            if len(manual_payments) > 15:
                payments_text += f"*...and {len(manual_payments) - 15} more*\n"
            
            embed.add_field(name="💰 Manual Payments", value=payments_text, inline=False)
        
        # Generated payments section
        if generated_payments:
            payments_text = ""
            for pid, payer_id, recipient_id, amount, szn, round_name in generated_payments[:15]:
                payer = interaction.guild.get_member(payer_id)
                recipient = interaction.guild.get_member(recipient_id)
                payer_name = payer.mention if payer else f"User {payer_id}"
                recipient_name = recipient.mention if recipient else f"User {recipient_id}"
                payments_text += f"• {payer_name} → {recipient_name}: **${amount:.2f}** (Szn {szn} {round_name})\n"
                total_outstanding += amount
            
            if len(generated_payments) > 15:
                payments_text += f"*...and {len(generated_payments) - 15} more*\n"
            
            embed.add_field(name="🏆 Playoff Dues", value=payments_text, inline=False)
        
        embed.add_field(name="💵 Total Outstanding", value=f"**${total_outstanding:.2f}**", inline=False)
        embed.set_footer(text="Use /markpaid to mark payments as complete")
        
        # Post to #payouts channel
        await payouts_channel.send(embed=embed)
        await interaction.followup.send(f"✅ Payment schedule posted to {payouts_channel.mention}!")

    @app_commands.command(name="createpayment", description="[Admin] Create a payment obligation")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        debtor="Who owes the money",
        creditor="Who is owed the money",
        amount="Amount owed",
        reason="Reason for the payment",
        season="Season number (optional)"
    )
    async def create_payment(
        self,
        interaction: discord.Interaction,
        debtor: discord.Member,
        creditor: discord.Member,
        amount: float,
        reason: str,
        season: Optional[int] = None
    ):
        """Create a manual payment obligation."""
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO manual_payments (season, debtor_id, creditor_id, amount, reason, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (season, debtor.id, creditor.id, amount, reason, interaction.user.id))
        
        payment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ Created payment #{payment_id}:\n"
            f"**{debtor.display_name}** owes **{creditor.display_name}** **${amount:.2f}**\n"
            f"Reason: {reason}",
            ephemeral=False
        )

    @app_commands.command(name="markpaid", description="Mark a payment as paid")
    @app_commands.describe(
        debtor="The person who paid",
        amount="Amount that was paid",
        reason="Optional note about the payment"
    )
    async def mark_paid(
        self,
        interaction: discord.Interaction,
        debtor: discord.Member,
        amount: float,
        reason: Optional[str] = None
    ):
        """Mark a payment as paid. Can be used by admin or the creditor."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if user is admin or the creditor
        is_admin = interaction.user.guild_permissions.administrator
        
        # Find matching unpaid payment
        cursor.execute('''
            SELECT payment_id, creditor_id, amount FROM manual_payments
            WHERE debtor_id = ? AND is_paid = 0 AND amount = ?
            ORDER BY created_at
            LIMIT 1
        ''', (debtor.id, amount))
        payment = cursor.fetchone()
        
        if not payment:
            # Try generated payments
            cursor.execute('''
                SELECT payment_id, payee_discord_id, amount FROM payments
                WHERE payer_discord_id = ? AND is_paid = 0 AND amount = ?
                ORDER BY season
                LIMIT 1
            ''', (debtor.id, amount))
            payment = cursor.fetchone()
            payment_type = 'generated'
        else:
            payment_type = 'manual'
        
        if not payment:
            await interaction.response.send_message(
                f"❌ No unpaid payment of ${amount:.2f} found from {debtor.display_name}",
                ephemeral=True
            )
            conn.close()
            return
        
        payment_id, creditor_id, pay_amount = payment
        
        # Check authorization
        if not is_admin and interaction.user.id != creditor_id:
            await interaction.response.send_message(
                "❌ Only admins or the person owed can mark payments as paid!",
                ephemeral=True
            )
            conn.close()
            return
        
        # Mark as paid
        if payment_type == 'manual':
            cursor.execute('''
                UPDATE manual_payments 
                SET is_paid = 1, paid_date = ?
                WHERE payment_id = ?
            ''', (datetime.now().isoformat(), payment_id))
        else:
            cursor.execute('''
                UPDATE payments 
                SET is_paid = 1, paid_date = ?
                WHERE payment_id = ?
            ''', (datetime.now().isoformat(), payment_id))
        
        conn.commit()
        conn.close()
        
        creditor = interaction.guild.get_member(creditor_id)
        creditor_name = creditor.display_name if creditor else "Unknown"
        
        await interaction.response.send_message(
            f"✅ Marked as **PAID**!\n"
            f"**{debtor.display_name}** paid **${amount:.2f}** to **{creditor_name}**"
            f"{f' - {reason}' if reason else ''}",
            ephemeral=False
        )

    @app_commands.command(name="topearners", description="View the top earners leaderboard")
    @app_commands.describe(season="Season to view (optional)")
    async def top_earners(self, interaction: discord.Interaction, season: Optional[int] = None):
        """Show leaderboard of top earners (combining wagers + season payouts)."""
        await interaction.response.defer()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get all completed wagers
        cursor.execute('''
            SELECT home_user_id, away_user_id, amount, winner_user_id
            FROM wagers WHERE winner_user_id IS NOT NULL
        ''')
        wagers = cursor.fetchall()
        
        # Get season payouts received
        cursor.execute('''
            SELECT payee_discord_id, SUM(amount) as total_earned
            FROM payments WHERE is_paid = 1
            GROUP BY payee_discord_id
        ''')
        season_earnings = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get season dues paid
        cursor.execute('''
            SELECT payer_discord_id, SUM(amount) as total_paid
            FROM payments WHERE is_paid = 1
            GROUP BY payer_discord_id
        ''')
        season_dues = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        # Calculate combined stats for each user
        user_stats = {}
        
        # Process wagers
        for home_user, away_user, amount, winner in wagers:
            for user_id in [home_user, away_user]:
                if user_id and user_id not in user_stats:
                    user_stats[user_id] = {'wager_won': 0.0, 'wager_lost': 0.0, 'season_earned': 0.0, 'season_paid': 0.0}
            
            if winner:
                loser = away_user if winner == home_user else home_user
                if winner:
                    user_stats[winner]['wager_won'] += amount
                if loser:
                    user_stats[loser]['wager_lost'] += amount
        
        # Add season earnings/dues
        all_users = set(list(season_earnings.keys()) + list(season_dues.keys()) + list(user_stats.keys()))
        for user_id in all_users:
            if user_id and user_id not in user_stats:
                user_stats[user_id] = {'wager_won': 0.0, 'wager_lost': 0.0, 'season_earned': 0.0, 'season_paid': 0.0}
            if user_id:
                user_stats[user_id]['season_earned'] = season_earnings.get(user_id, 0.0)
                user_stats[user_id]['season_paid'] = season_dues.get(user_id, 0.0)
        
        if not user_stats:
            await interaction.followup.send("📊 No earnings data available yet!", ephemeral=True)
            return
        
        # Calculate net and sort
        def calc_net(stats):
            return (stats['wager_won'] - stats['wager_lost']) + (stats['season_earned'] - stats['season_paid'])
        
        sorted_users = sorted(user_stats.items(), key=lambda x: calc_net(x[1]), reverse=True)[:10]
        
        embed = discord.Embed(
            title=f"🏆 Top Earners (All Time)",
            description="Combined wager wins + season payouts",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        leaderboard = ""
        medals = ["🥇", "🥈", "🥉"]
        
        for i, (user_id, stats) in enumerate(sorted_users):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"<@{user_id}>"
            net = calc_net(stats)
            wager_net = stats['wager_won'] - stats['wager_lost']
            season_net = stats['season_earned'] - stats['season_paid']
            medal = medals[i] if i < 3 else f"{i+1}."
            leaderboard += f"{medal} **{name}**: **${net:+.2f}**\n    └ Wagers: ${wager_net:+.2f} | Season: ${season_net:+.2f}\n"
        
        embed.description = leaderboard or "No data yet"
        embed.set_footer(text="Keep grinding! 💰")
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="toplosers", description="View the biggest losers leaderboard")
    @app_commands.describe(season="Season to view (optional)")
    async def top_losers(self, interaction: discord.Interaction, season: Optional[int] = None):
        """Show leaderboard of biggest losers (combining wagers + season dues)."""
        await interaction.response.defer()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get all completed wagers
        cursor.execute('''
            SELECT home_user_id, away_user_id, amount, winner_user_id
            FROM wagers WHERE winner_user_id IS NOT NULL
        ''')
        wagers = cursor.fetchall()
        
        # Get season payouts received
        cursor.execute('''
            SELECT payee_discord_id, SUM(amount) as total_earned
            FROM payments WHERE is_paid = 1
            GROUP BY payee_discord_id
        ''')
        season_earnings = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get season dues paid
        cursor.execute('''
            SELECT payer_discord_id, SUM(amount) as total_paid
            FROM payments WHERE is_paid = 1
            GROUP BY payer_discord_id
        ''')
        season_dues = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        # Calculate combined stats for each user
        user_stats = {}
        
        # Process wagers
        for home_user, away_user, amount, winner in wagers:
            for user_id in [home_user, away_user]:
                if user_id and user_id not in user_stats:
                    user_stats[user_id] = {'wager_won': 0.0, 'wager_lost': 0.0, 'season_earned': 0.0, 'season_paid': 0.0}
            
            if winner:
                loser = away_user if winner == home_user else home_user
                if winner:
                    user_stats[winner]['wager_won'] += amount
                if loser:
                    user_stats[loser]['wager_lost'] += amount
        
        # Add season earnings/dues
        all_users = set(list(season_earnings.keys()) + list(season_dues.keys()) + list(user_stats.keys()))
        for user_id in all_users:
            if user_id and user_id not in user_stats:
                user_stats[user_id] = {'wager_won': 0.0, 'wager_lost': 0.0, 'season_earned': 0.0, 'season_paid': 0.0}
            if user_id:
                user_stats[user_id]['season_earned'] = season_earnings.get(user_id, 0.0)
                user_stats[user_id]['season_paid'] = season_dues.get(user_id, 0.0)
        
        if not user_stats:
            await interaction.followup.send("📊 No data available yet!", ephemeral=True)
            return
        
        # Calculate net and sort (ascending for losers)
        def calc_net(stats):
            return (stats['wager_won'] - stats['wager_lost']) + (stats['season_earned'] - stats['season_paid'])
        
        # Only show users with negative net
        losers = [(uid, stats) for uid, stats in user_stats.items() if calc_net(stats) < 0]
        sorted_users = sorted(losers, key=lambda x: calc_net(x[1]))[:10]
        
        embed = discord.Embed(
            title=f"📉 Biggest Losers (All Time)",
            description="Combined wager losses + season dues paid",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        leaderboard = ""
        shame_emojis = ["💩", "🤡", "😭"]
        
        for i, (user_id, stats) in enumerate(sorted_users):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"<@{user_id}>"
            net = calc_net(stats)
            wager_net = stats['wager_won'] - stats['wager_lost']
            season_net = stats['season_earned'] - stats['season_paid']
            emoji = shame_emojis[i] if i < 3 else f"{i+1}."
            leaderboard += f"{emoji} **{name}**: **${net:+.2f}**\n    └ Wagers: ${wager_net:+.2f} | Season: ${season_net:+.2f}\n"
        
        embed.description = leaderboard or "No losers yet! Everyone's winning! 🎉"
        embed.set_footer(text="Git gud! 🎮")
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="clearpayment", description="[Admin] Delete a specific payment")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        debtor="The person who owes",
        creditor="The person owed",
        amount="The amount to clear"
    )
    async def clear_payment(
        self,
        interaction: discord.Interaction,
        debtor: discord.Member,
        creditor: discord.Member,
        amount: float
    ):
        """Delete a specific payment obligation."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM manual_payments
            WHERE debtor_id = ? AND creditor_id = ? AND amount = ? AND is_paid = 0
        ''', (debtor.id, creditor.id, amount))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted:
            await interaction.response.send_message(
                f"✅ Deleted payment: {debtor.display_name} → {creditor.display_name}: ${amount:.2f}"
            )
        else:
            await interaction.response.send_message(
                f"❌ No matching unpaid payment found",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(PaymentsCog(bot))
