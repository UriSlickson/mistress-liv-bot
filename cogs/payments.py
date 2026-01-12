"""
Payments Cog - User-facing payment tracking and management
CONSOLIDATED COMMANDS:
/payments owedtome - See who owes you money
/payments iowe - See who you owe money to
/payments status - View your complete payment status
/payments schedule - View all outstanding payments
/payments create - Create a payment obligation (admin)
/payments paid - Mark a payment as paid
/payments clear - Delete a payment (admin)

/leaderboard earners - Top earners
/leaderboard losers - Biggest losers
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

    # ==================== PAYMENTS COMMAND GROUP ====================
    
    payments_group = app_commands.Group(name="payments", description="Payment tracking commands")
    
    @payments_group.command(name="owedtome", description="See who owes you money")
    async def payments_owed_to_me(self, interaction: discord.Interaction):
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
            await interaction.response.send_message("✅ No one owes you money right now!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="💰 Money Owed TO You",
            color=discord.Color.green()
        )
        
        total = 0
        
        if generated_debts:
            debt_text = ""
            for payment_id, debtor_id, amount, season, round_name in generated_debts:
                member = interaction.guild.get_member(debtor_id)
                name = member.display_name if member else f"User {debtor_id}"
                debt_text += f"• **{name}**: ${amount:.2f} (SZN {season})\n"
                total += amount
            embed.add_field(name="📊 Playoff Payouts", value=debt_text[:1024], inline=False)
        
        if manual_debts:
            debt_text = ""
            for payment_id, debtor_id, amount, reason, created_at in manual_debts:
                member = interaction.guild.get_member(debtor_id)
                name = member.display_name if member else f"User {debtor_id}"
                debt_text += f"• **{name}**: ${amount:.2f} - {reason or 'No reason'}\n"
                total += amount
            embed.add_field(name="📝 Other Payments", value=debt_text[:1024], inline=False)
        
        embed.set_footer(text=f"Total Owed to You: ${total:.2f}")
        await interaction.response.send_message(embed=embed)
    
    @payments_group.command(name="iowe", description="See who you owe money to")
    async def payments_i_owe(self, interaction: discord.Interaction):
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
            await interaction.response.send_message("✅ You don't owe anyone money!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="💸 Money You Owe",
            color=discord.Color.red()
        )
        
        total = 0
        
        if generated_debts:
            debt_text = ""
            for payment_id, creditor_id, amount, season, round_name in generated_debts:
                member = interaction.guild.get_member(creditor_id)
                name = member.display_name if member else f"User {creditor_id}"
                debt_text += f"• **{name}**: ${amount:.2f} (SZN {season})\n"
                total += amount
            embed.add_field(name="📊 Playoff Payouts", value=debt_text[:1024], inline=False)
        
        if manual_debts:
            debt_text = ""
            for payment_id, creditor_id, amount, reason, created_at in manual_debts:
                member = interaction.guild.get_member(creditor_id)
                name = member.display_name if member else f"User {creditor_id}"
                debt_text += f"• **{name}**: ${amount:.2f} - {reason or 'No reason'}\n"
                total += amount
            embed.add_field(name="📝 Other Payments", value=debt_text[:1024], inline=False)
        
        embed.set_footer(text=f"Total You Owe: ${total:.2f}")
        await interaction.response.send_message(embed=embed)
    
    @payments_group.command(name="status", description="View your complete payment status")
    async def payments_status(self, interaction: discord.Interaction):
        """View complete payment status for the user."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Money owed to user
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) FROM manual_payments
            WHERE creditor_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        manual_owed_to = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) FROM payments
            WHERE payee_discord_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        generated_owed_to = cursor.fetchone()[0]
        
        # Money user owes
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) FROM manual_payments
            WHERE debtor_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        manual_owes = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) FROM payments
            WHERE payer_discord_id = ? AND is_paid = 0
        ''', (interaction.user.id,))
        generated_owes = cursor.fetchone()[0]
        
        conn.close()
        
        total_owed_to = manual_owed_to + generated_owed_to
        total_owes = manual_owes + generated_owes
        net = total_owed_to - total_owes
        
        embed = discord.Embed(
            title=f"💰 Payment Status - {interaction.user.display_name}",
            color=discord.Color.green() if net >= 0 else discord.Color.red()
        )
        
        embed.add_field(name="💵 Owed to You", value=f"${total_owed_to:.2f}", inline=True)
        embed.add_field(name="💸 You Owe", value=f"${total_owes:.2f}", inline=True)
        embed.add_field(name="📊 Net", value=f"${net:+.2f}", inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @payments_group.command(name="schedule", description="View all outstanding payments (posts to #payouts)")
    @app_commands.checks.has_permissions(administrator=True)
    async def payments_schedule(self, interaction: discord.Interaction):
        """Post all outstanding payments to #payouts channel."""
        await interaction.response.defer()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT payer_discord_id, payee_discord_id, amount, season, round
            FROM payments WHERE is_paid = 0
            ORDER BY season DESC, amount DESC
        ''')
        payments = cursor.fetchall()
        conn.close()
        
        if not payments:
            await interaction.followup.send("✅ No outstanding payments!")
            return
        
        embed = discord.Embed(
            title="📋 Outstanding Payments",
            color=discord.Color.blue()
        )
        
        payment_text = ""
        total = 0
        for payer_id, payee_id, amount, season, round_name in payments[:25]:
            payer = interaction.guild.get_member(payer_id)
            payee = interaction.guild.get_member(payee_id)
            payer_name = payer.display_name if payer else f"User {payer_id}"
            payee_name = payee.display_name if payee else f"User {payee_id}"
            payment_text += f"• {payer_name} → {payee_name}: ${amount:.2f}\n"
            total += amount
        
        embed.description = payment_text
        embed.set_footer(text=f"Total Outstanding: ${total:.2f}")
        
        await interaction.followup.send(embed=embed)
    
    @payments_group.command(name="create", description="[Admin] Create a payment obligation")
    @app_commands.describe(
        debtor="User who owes money",
        creditor="User who is owed money",
        amount="Amount owed",
        reason="Reason for the payment"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def payments_create(
        self,
        interaction: discord.Interaction,
        debtor: discord.Member,
        creditor: discord.Member,
        amount: float,
        reason: Optional[str] = None
    ):
        """Create a manual payment obligation."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO manual_payments (debtor_id, creditor_id, amount, reason, created_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (debtor.id, creditor.id, amount, reason, interaction.user.id))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="💰 Payment Created",
            color=discord.Color.green()
        )
        embed.add_field(name="Debtor", value=debtor.mention, inline=True)
        embed.add_field(name="Creditor", value=creditor.mention, inline=True)
        embed.add_field(name="Amount", value=f"${amount:.2f}", inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @payments_group.command(name="paid", description="Mark a payment as paid")
    @app_commands.describe(debtor="User who paid you")
    async def payments_paid(self, interaction: discord.Interaction, debtor: discord.Member):
        """Mark payments from a user as paid."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Update manual payments
        cursor.execute('''
            UPDATE manual_payments SET is_paid = 1, paid_date = ?
            WHERE debtor_id = ? AND creditor_id = ? AND is_paid = 0
        ''', (datetime.now().isoformat(), debtor.id, interaction.user.id))
        manual_count = cursor.rowcount
        
        # Update generated payments
        cursor.execute('''
            UPDATE payments SET is_paid = 1, paid_date = ?
            WHERE payer_discord_id = ? AND payee_discord_id = ? AND is_paid = 0
        ''', (datetime.now().isoformat(), debtor.id, interaction.user.id))
        generated_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        total = manual_count + generated_count
        if total > 0:
            await interaction.response.send_message(
                f"✅ Marked {total} payment(s) from {debtor.mention} as paid!"
            )
        else:
            await interaction.response.send_message(
                f"❌ No unpaid payments found from {debtor.mention}.",
                ephemeral=True
            )
    
    @payments_group.command(name="clear", description="[Admin] Delete a specific payment")
    @app_commands.describe(
        debtor="User who owes",
        creditor="User who is owed"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def payments_clear(
        self,
        interaction: discord.Interaction,
        debtor: discord.Member,
        creditor: discord.Member
    ):
        """Delete payment records between two users."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM manual_payments
            WHERE debtor_id = ? AND creditor_id = ?
        ''', (debtor.id, creditor.id))
        manual_count = cursor.rowcount
        
        cursor.execute('''
            DELETE FROM payments
            WHERE payer_discord_id = ? AND payee_discord_id = ?
        ''', (debtor.id, creditor.id))
        generated_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        total = manual_count + generated_count
        await interaction.response.send_message(
            f"✅ Deleted {total} payment record(s) between {debtor.mention} and {creditor.mention}."
        )

    # ==================== LEADERBOARD COMMAND GROUP ====================
    
    leaderboard_group = app_commands.Group(name="leaderboard", description="View leaderboards")
    
    @leaderboard_group.command(name="earners", description="View the top earners leaderboard")
    async def leaderboard_earners(self, interaction: discord.Interaction):
        """Show top earners leaderboard."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get total earnings per user (money owed to them that's been paid)
        cursor.execute('''
            SELECT payee_discord_id, SUM(amount) as total
            FROM payments WHERE is_paid = 1
            GROUP BY payee_discord_id
            ORDER BY total DESC
            LIMIT 15
        ''')
        earners = cursor.fetchall()
        conn.close()
        
        if not earners:
            await interaction.response.send_message("📊 No earnings data yet!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🏆 Top Earners",
            color=discord.Color.gold()
        )
        
        leaderboard = ""
        for i, (user_id, total) in enumerate(earners, 1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            leaderboard += f"{medal} **{name}**: ${total:.2f}\n"
        
        embed.description = leaderboard
        await interaction.response.send_message(embed=embed)
    
    @leaderboard_group.command(name="losers", description="View the biggest losers leaderboard")
    async def leaderboard_losers(self, interaction: discord.Interaction):
        """Show biggest losers leaderboard."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get total paid out per user
        cursor.execute('''
            SELECT payer_discord_id, SUM(amount) as total
            FROM payments WHERE is_paid = 1
            GROUP BY payer_discord_id
            ORDER BY total DESC
            LIMIT 15
        ''')
        losers = cursor.fetchall()
        conn.close()
        
        if not losers:
            await interaction.response.send_message("📊 No payment data yet!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="💸 Biggest Losers",
            color=discord.Color.red()
        )
        
        leaderboard = ""
        for i, (user_id, total) in enumerate(losers, 1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            leaderboard += f"{medal} **{name}**: ${total:.2f}\n"
        
        embed.description = leaderboard
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(PaymentsCog(bot))
"""
