"""
Prediction Markets Cog - Kalshi-Style Trading System
Features:
- Dynamic Yes/No markets with auto-matching
- Bot counterparty for instant trade clears
- Order book tracking with limit orders
- Automated resolution via Snallabot data
- Leaderboards and position tracking
- 6% house fee on profits
- $10 minimum trades in $10 increments only

Commands:
/market create - Create a new prediction market
/market view - View all active markets
/market status - View detailed market status
/trade - Place a trade (buy/sell Yes/No)
/cancelorder - Cancel an open order
/mypositions - View your positions and P/L
/predictionleaderboard - View rankings
/resolvemarket - [Admin] Resolve a market
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from decimal import Decimal, ROUND_HALF_UP
import aiohttp

logger = logging.getLogger('MistressLIV.PredictionMarkets')

# Constants
HOUSE_FEE_RATE = 0.06  # 6% fee on profits
MIN_TRADE_AMOUNT = 10  # $10 minimum
TRADE_INCREMENT = 10   # Must be in $10 increments
MAX_SHARES_PER_USER_PER_MARKET = 500  # Volume cap
BOT_LIQUIDITY_SEED = 100  # Initial bot liquidity per side
SNALLABOT_API_BASE = "https://snallabot.me"

# Price is in cents (0-100), represents probability
MIN_PRICE = 5   # 5 cents minimum
MAX_PRICE = 95  # 95 cents maximum

# NFC Requirement
NFC_MIN_VOLUME_REQUIREMENT = 100  # $100 minimum for NFC members
NFC_DEADLINE_WEEK = 18  # Must be met by end of Week 18
NFC_TEAMS = ['ARI', 'ATL', 'CAR', 'CHI', 'DAL', 'DET', 'GB', 'LAR', 
             'MIN', 'NO', 'NYG', 'PHI', 'SF', 'SEA', 'TB', 'WAS',
             'Cardinals', 'Falcons', 'Panthers', 'Bears', 'Cowboys', 'Lions',
             'Packers', 'Rams', 'Vikings', 'Saints', 'Giants', 'Eagles',
             '49ers', 'Seahawks', 'Buccaneers', 'Commanders']


class PredictionMarketsCog(commands.Cog):
    """Cog for Kalshi-style prediction markets."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._init_tables()
        self.update_market_odds.start()
        self.check_nfc_requirements.start()
    
    def cog_unload(self):
        self.update_market_odds.cancel()
        self.check_nfc_requirements.cancel()
    
    def _init_tables(self):
        """Initialize prediction markets database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Markets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_markets (
                market_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                resolution_week INTEGER,
                resolution_type TEXT DEFAULT 'manual',
                resolution_criteria TEXT,
                status TEXT DEFAULT 'active',
                result TEXT,
                resolved_at TEXT,
                yes_price INTEGER DEFAULT 50,
                total_volume INTEGER DEFAULT 0,
                channel_id INTEGER
            )
        ''')
        
        # Orders table (order book)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                side TEXT NOT NULL,
                direction TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price INTEGER NOT NULL,
                filled_quantity INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                created_at TEXT NOT NULL,
                filled_at TEXT,
                is_bot_order INTEGER DEFAULT 0,
                FOREIGN KEY (market_id) REFERENCES prediction_markets(market_id)
            )
        ''')
        
        # Positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                yes_shares INTEGER DEFAULT 0,
                no_shares INTEGER DEFAULT 0,
                avg_yes_price INTEGER DEFAULT 0,
                avg_no_price INTEGER DEFAULT 0,
                total_invested INTEGER DEFAULT 0,
                UNIQUE(market_id, user_id),
                FOREIGN KEY (market_id) REFERENCES prediction_markets(market_id)
            )
        ''')
        
        # Trades table (history)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                buyer_id INTEGER NOT NULL,
                seller_id INTEGER NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price INTEGER NOT NULL,
                total_amount INTEGER NOT NULL,
                executed_at TEXT NOT NULL,
                buyer_order_id INTEGER,
                seller_order_id INTEGER,
                FOREIGN KEY (market_id) REFERENCES prediction_markets(market_id)
            )
        ''')
        
        # User profits table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_profits (
                user_id INTEGER PRIMARY KEY,
                total_profit INTEGER DEFAULT 0,
                total_volume INTEGER DEFAULT 0,
                markets_won INTEGER DEFAULT 0,
                markets_lost INTEGER DEFAULT 0,
                markets_participated INTEGER DEFAULT 0
            )
        ''')
        
        # House pot table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_house_pot (
                id INTEGER PRIMARY KEY DEFAULT 1,
                total_fees INTEGER DEFAULT 0,
                last_updated TEXT
            )
        ''')
        
        # Initialize house pot if not exists
        cursor.execute('INSERT OR IGNORE INTO prediction_house_pot (id, total_fees) VALUES (1, 0)')
        
        conn.commit()
        conn.close()
        logger.info("Prediction markets tables initialized")
    
    def _generate_market_id(self) -> str:
        """Generate a unique market ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM prediction_markets')
        count = cursor.fetchone()[0]
        conn.close()
        return f"MKT{count + 1:03d}"
    
    def _validate_trade_amount(self, amount: int) -> Tuple[bool, str]:
        """Validate trade amount is in $10 increments."""
        if amount < MIN_TRADE_AMOUNT:
            return False, f"Minimum trade is ${MIN_TRADE_AMOUNT}"
        if amount % TRADE_INCREMENT != 0:
            return False, f"Trades must be in ${TRADE_INCREMENT} increments (e.g., $10, $20, $30)"
        return True, ""
    
    def _get_user_position(self, market_id: str, user_id: int) -> Dict:
        """Get user's current position in a market."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT yes_shares, no_shares, avg_yes_price, avg_no_price, total_invested
            FROM prediction_positions
            WHERE market_id = ? AND user_id = ?
        ''', (market_id, user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'yes_shares': row[0],
                'no_shares': row[1],
                'avg_yes_price': row[2],
                'avg_no_price': row[3],
                'total_invested': row[4]
            }
        return {'yes_shares': 0, 'no_shares': 0, 'avg_yes_price': 0, 'avg_no_price': 0, 'total_invested': 0}
    
    def _update_position(self, market_id: str, user_id: int, side: str, quantity: int, price: int, is_buy: bool):
        """Update user's position after a trade."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get current position
        cursor.execute('''
            SELECT yes_shares, no_shares, avg_yes_price, avg_no_price, total_invested
            FROM prediction_positions
            WHERE market_id = ? AND user_id = ?
        ''', (market_id, user_id))
        row = cursor.fetchone()
        
        if row:
            yes_shares, no_shares, avg_yes, avg_no, invested = row
        else:
            yes_shares, no_shares, avg_yes, avg_no, invested = 0, 0, 0, 0, 0
        
        trade_value = quantity * price
        
        if side == 'Yes':
            if is_buy:
                # Buying Yes shares
                new_total = yes_shares + quantity
                if new_total > 0:
                    avg_yes = ((yes_shares * avg_yes) + trade_value) // new_total
                yes_shares = new_total
                invested += trade_value
            else:
                # Selling Yes shares
                yes_shares = max(0, yes_shares - quantity)
                invested -= trade_value
        else:  # No
            if is_buy:
                # Buying No shares
                new_total = no_shares + quantity
                if new_total > 0:
                    avg_no = ((no_shares * avg_no) + trade_value) // new_total
                no_shares = new_total
                invested += trade_value
            else:
                # Selling No shares
                no_shares = max(0, no_shares - quantity)
                invested -= trade_value
        
        cursor.execute('''
            INSERT OR REPLACE INTO prediction_positions 
            (market_id, user_id, yes_shares, no_shares, avg_yes_price, avg_no_price, total_invested)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (market_id, user_id, yes_shares, no_shares, avg_yes, avg_no, invested))
        
        conn.commit()
        conn.close()
    
    def _get_order_book(self, market_id: str) -> Dict:
        """Get the current order book for a market."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get open buy orders for Yes (sorted by price desc - best bids first)
        cursor.execute('''
            SELECT order_id, user_id, quantity - filled_quantity as remaining, price, is_bot_order
            FROM prediction_orders
            WHERE market_id = ? AND side = 'Yes' AND direction = 'buy' AND status = 'open'
            AND quantity > filled_quantity
            ORDER BY price DESC, created_at ASC
        ''', (market_id,))
        yes_bids = cursor.fetchall()
        
        # Get open sell orders for Yes (sorted by price asc - best asks first)
        cursor.execute('''
            SELECT order_id, user_id, quantity - filled_quantity as remaining, price, is_bot_order
            FROM prediction_orders
            WHERE market_id = ? AND side = 'Yes' AND direction = 'sell' AND status = 'open'
            AND quantity > filled_quantity
            ORDER BY price ASC, created_at ASC
        ''', (market_id,))
        yes_asks = cursor.fetchall()
        
        # Get open buy orders for No
        cursor.execute('''
            SELECT order_id, user_id, quantity - filled_quantity as remaining, price, is_bot_order
            FROM prediction_orders
            WHERE market_id = ? AND side = 'No' AND direction = 'buy' AND status = 'open'
            AND quantity > filled_quantity
            ORDER BY price DESC, created_at ASC
        ''', (market_id,))
        no_bids = cursor.fetchall()
        
        # Get open sell orders for No
        cursor.execute('''
            SELECT order_id, user_id, quantity - filled_quantity as remaining, price, is_bot_order
            FROM prediction_orders
            WHERE market_id = ? AND side = 'No' AND direction = 'sell' AND status = 'open'
            AND quantity > filled_quantity
            ORDER BY price ASC, created_at ASC
        ''', (market_id,))
        no_asks = cursor.fetchall()
        
        conn.close()
        
        return {
            'yes_bids': yes_bids,
            'yes_asks': yes_asks,
            'no_bids': no_bids,
            'no_asks': no_asks
        }
    
    def _match_order(self, market_id: str, user_id: int, side: str, direction: str, 
                     quantity: int, limit_price: int) -> Dict:
        """
        Match an order against the order book.
        Returns dict with filled_quantity, avg_price, remaining, trades executed.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        filled_quantity = 0
        total_cost = 0
        trades = []
        remaining = quantity
        
        # Determine which side of the book to match against
        if direction == 'buy':
            # Buying: match against sell orders (asks) at or below limit price
            cursor.execute('''
                SELECT order_id, user_id, quantity - filled_quantity as remaining, price, is_bot_order
                FROM prediction_orders
                WHERE market_id = ? AND side = ? AND direction = 'sell' AND status = 'open'
                AND quantity > filled_quantity AND price <= ?
                ORDER BY price ASC, created_at ASC
            ''', (market_id, side, limit_price))
        else:
            # Selling: match against buy orders (bids) at or above limit price
            cursor.execute('''
                SELECT order_id, user_id, quantity - filled_quantity as remaining, price, is_bot_order
                FROM prediction_orders
                WHERE market_id = ? AND side = ? AND direction = 'buy' AND status = 'open'
                AND quantity > filled_quantity AND price >= ?
                ORDER BY price DESC, created_at ASC
            ''', (market_id, side, limit_price))
        
        matching_orders = cursor.fetchall()
        
        for order_id, seller_id, available, price, is_bot in matching_orders:
            if remaining <= 0:
                break
            
            # Don't match against own orders
            if seller_id == user_id:
                continue
            
            fill_qty = min(remaining, available)
            fill_cost = fill_qty * price
            
            # Update the matched order
            cursor.execute('''
                UPDATE prediction_orders 
                SET filled_quantity = filled_quantity + ?
                WHERE order_id = ?
            ''', (fill_qty, order_id))
            
            # Check if order is fully filled
            cursor.execute('''
                UPDATE prediction_orders 
                SET status = 'filled', filled_at = ?
                WHERE order_id = ? AND filled_quantity >= quantity
            ''', (datetime.now().isoformat(), order_id))
            
            # Record the trade
            if direction == 'buy':
                buyer_id, seller_id_trade = user_id, seller_id
            else:
                buyer_id, seller_id_trade = seller_id, user_id
            
            cursor.execute('''
                INSERT INTO prediction_trades 
                (market_id, buyer_id, seller_id, side, quantity, price, total_amount, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (market_id, buyer_id, seller_id_trade, side, fill_qty, price, fill_cost, 
                  datetime.now().isoformat()))
            
            # Update positions
            if direction == 'buy':
                self._update_position(market_id, user_id, side, fill_qty, price, True)
                self._update_position(market_id, seller_id, side, fill_qty, price, False)
            else:
                self._update_position(market_id, user_id, side, fill_qty, price, False)
                self._update_position(market_id, seller_id, side, fill_qty, price, True)
            
            trades.append({
                'order_id': order_id,
                'counterparty': seller_id,
                'quantity': fill_qty,
                'price': price,
                'is_bot': is_bot
            })
            
            filled_quantity += fill_qty
            total_cost += fill_cost
            remaining -= fill_qty
        
        # Update market volume
        if filled_quantity > 0:
            cursor.execute('''
                UPDATE prediction_markets 
                SET total_volume = total_volume + ?
                WHERE market_id = ?
            ''', (total_cost, market_id))
        
        conn.commit()
        conn.close()
        
        avg_price = total_cost // filled_quantity if filled_quantity > 0 else 0
        
        return {
            'filled_quantity': filled_quantity,
            'avg_price': avg_price,
            'total_cost': total_cost,
            'remaining': remaining,
            'trades': trades
        }
    
    def _create_bot_order(self, market_id: str, side: str, direction: str, quantity: int, price: int):
        """Create a bot counterparty order for instant fills."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO prediction_orders 
            (market_id, user_id, side, direction, quantity, price, status, created_at, is_bot_order)
            VALUES (?, 0, ?, ?, ?, ?, 'open', ?, 1)
        ''', (market_id, side, direction, quantity, price, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def _seed_bot_liquidity(self, market_id: str, initial_price: int = 50):
        """Seed initial bot liquidity for a new market."""
        # Bot provides liquidity on both sides
        # Yes side: sell at initial_price + spread, buy at initial_price - spread
        # No side: sell at (100 - initial_price) + spread, buy at (100 - initial_price) - spread
        
        spread = 5  # 5 cent spread
        
        # Yes liquidity
        self._create_bot_order(market_id, 'Yes', 'sell', BOT_LIQUIDITY_SEED, min(initial_price + spread, MAX_PRICE))
        self._create_bot_order(market_id, 'Yes', 'buy', BOT_LIQUIDITY_SEED, max(initial_price - spread, MIN_PRICE))
        
        # No liquidity (No price = 100 - Yes price)
        no_price = 100 - initial_price
        self._create_bot_order(market_id, 'No', 'sell', BOT_LIQUIDITY_SEED, min(no_price + spread, MAX_PRICE))
        self._create_bot_order(market_id, 'No', 'buy', BOT_LIQUIDITY_SEED, max(no_price - spread, MIN_PRICE))
    
    def _fill_with_bot(self, market_id: str, user_id: int, side: str, direction: str, 
                       quantity: int, price: int) -> Dict:
        """Fill remaining order quantity with bot counterparty."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Bot takes the opposite side
        bot_direction = 'sell' if direction == 'buy' else 'buy'
        
        # Create bot order and immediately fill it
        cursor.execute('''
            INSERT INTO prediction_orders 
            (market_id, user_id, side, direction, quantity, price, filled_quantity, status, created_at, filled_at, is_bot_order)
            VALUES (?, 0, ?, ?, ?, ?, ?, 'filled', ?, ?, 1)
        ''', (market_id, side, bot_direction, quantity, price, quantity, 
              datetime.now().isoformat(), datetime.now().isoformat()))
        
        bot_order_id = cursor.lastrowid
        
        # Record the trade
        if direction == 'buy':
            buyer_id, seller_id = user_id, 0
        else:
            buyer_id, seller_id = 0, user_id
        
        total_amount = quantity * price
        
        cursor.execute('''
            INSERT INTO prediction_trades 
            (market_id, buyer_id, seller_id, side, quantity, price, total_amount, executed_at, buyer_order_id, seller_order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (market_id, buyer_id, seller_id, side, quantity, price, total_amount,
              datetime.now().isoformat(), None, bot_order_id))
        
        # Update user position
        self._update_position(market_id, user_id, side, quantity, price, direction == 'buy')
        
        # Update market volume
        cursor.execute('''
            UPDATE prediction_markets 
            SET total_volume = total_volume + ?
            WHERE market_id = ?
        ''', (total_amount, market_id))
        
        conn.commit()
        conn.close()
        
        return {
            'filled_quantity': quantity,
            'avg_price': price,
            'total_cost': total_amount,
            'is_bot_fill': True
        }
    
    def _update_market_price(self, market_id: str):
        """Update market price based on recent trades."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get recent Yes trades (last 10)
        cursor.execute('''
            SELECT price, quantity FROM prediction_trades
            WHERE market_id = ? AND side = 'Yes'
            ORDER BY executed_at DESC
            LIMIT 10
        ''', (market_id,))
        trades = cursor.fetchall()
        
        if trades:
            # Volume-weighted average price
            total_value = sum(p * q for p, q in trades)
            total_quantity = sum(q for _, q in trades)
            new_price = total_value // total_quantity if total_quantity > 0 else 50
            new_price = max(MIN_PRICE, min(MAX_PRICE, new_price))
            
            cursor.execute('''
                UPDATE prediction_markets SET yes_price = ? WHERE market_id = ?
            ''', (new_price, market_id))
        
        conn.commit()
        conn.close()
    
    def _calculate_user_pnl(self, market_id: str, user_id: int, current_yes_price: int) -> Dict:
        """Calculate unrealized P/L for a user's position."""
        position = self._get_user_position(market_id, user_id)
        
        yes_value = position['yes_shares'] * current_yes_price
        no_value = position['no_shares'] * (100 - current_yes_price)
        current_value = yes_value + no_value
        
        unrealized_pnl = current_value - position['total_invested']
        
        return {
            'yes_shares': position['yes_shares'],
            'no_shares': position['no_shares'],
            'current_value': current_value,
            'invested': position['total_invested'],
            'unrealized_pnl': unrealized_pnl
        }
    
    async def _get_snallabot_config(self, guild_id: int) -> Optional[Dict]:
        """Get Snallabot configuration."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT league_id, platform, current_season FROM league_config 
            WHERE guild_id = ? AND is_active = 1
        ''', (guild_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {'league_id': row[0], 'platform': row[1], 'current_season': row[2]}
        return None
    
    # ==================== COMMAND GROUP ====================
    
    market_group = app_commands.Group(name="market", description="Prediction market commands")
    
    @market_group.command(name="create", description="Create a new prediction market")
    @app_commands.describe(
        question="The prediction question (e.g., 'Will Mahomes throw 4000+ yards?')",
        resolution_week="Week number when market resolves (optional)",
        initial_odds="Initial Yes probability (5-95, default 50)"
    )
    async def create_market(
        self, 
        interaction: discord.Interaction, 
        question: str,
        resolution_week: Optional[int] = None,
        initial_odds: Optional[int] = 50
    ):
        """Create a new prediction market."""
        await interaction.response.defer()
        
        # Validate initial odds
        initial_odds = max(MIN_PRICE, min(MAX_PRICE, initial_odds))
        
        market_id = self._generate_market_id()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Find or create prediction-markets channel
        channel = discord.utils.get(interaction.guild.text_channels, name='prediction-markets')
        channel_id = channel.id if channel else interaction.channel.id
        
        cursor.execute('''
            INSERT INTO prediction_markets 
            (market_id, guild_id, question, created_by, created_at, resolution_week, yes_price, channel_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (market_id, interaction.guild.id, question, interaction.user.id,
              datetime.now().isoformat(), resolution_week, initial_odds, channel_id))
        
        conn.commit()
        conn.close()
        
        # Seed bot liquidity
        self._seed_bot_liquidity(market_id, initial_odds)
        
        # Create embed
        embed = discord.Embed(
            title=f"🎯 New Prediction Market: {market_id}",
            description=f"**{question}**",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📊 Current Odds",
            value=f"**Yes:** {initial_odds}¢ ({initial_odds}%)\n**No:** {100-initial_odds}¢ ({100-initial_odds}%)",
            inline=True
        )
        
        embed.add_field(
            name="📅 Resolution",
            value=f"Week {resolution_week}" if resolution_week else "Manual",
            inline=True
        )
        
        embed.add_field(
            name="💰 Trading Rules",
            value=f"• Minimum: ${MIN_TRADE_AMOUNT}\n• Increments: ${TRADE_INCREMENT}\n• Max per user: {MAX_SHARES_PER_USER_PER_MARKET} shares",
            inline=False
        )
        
        embed.add_field(
            name="📈 How to Trade",
            value=f"`/trade {market_id} Yes buy 10 {initial_odds}` - Buy $10 of Yes at {initial_odds}¢\n"
                  f"`/trade {market_id} No buy 20 {100-initial_odds}` - Buy $20 of No at {100-initial_odds}¢",
            inline=False
        )
        
        embed.set_footer(text=f"Created by {interaction.user.display_name} • 6% fee on profits")
        
        await interaction.followup.send(embed=embed)
        
        # Also post to prediction-markets channel if different
        if channel and channel.id != interaction.channel.id:
            await channel.send(embed=embed)
    
    @market_group.command(name="view", description="View all active prediction markets")
    async def view_markets(self, interaction: discord.Interaction):
        """List all active markets with current odds."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT market_id, question, yes_price, total_volume, resolution_week, created_by
            FROM prediction_markets
            WHERE guild_id = ? AND status = 'active'
            ORDER BY created_at DESC
        ''', (interaction.guild.id,))
        
        markets = cursor.fetchall()
        conn.close()
        
        if not markets:
            await interaction.followup.send("📭 No active prediction markets. Create one with `/market create`!")
            return
        
        embed = discord.Embed(
            title="🎯 Active Prediction Markets",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        for market_id, question, yes_price, volume, res_week, creator_id in markets:
            # Get user's position
            position = self._get_user_position(market_id, interaction.user.id)
            pos_str = ""
            if position['yes_shares'] > 0 or position['no_shares'] > 0:
                pos_str = f"\n📍 Your position: {position['yes_shares']} Yes, {position['no_shares']} No"
            
            res_str = f"Week {res_week}" if res_week else "Manual"
            
            embed.add_field(
                name=f"{market_id}: {question[:50]}{'...' if len(question) > 50 else ''}",
                value=f"**Yes:** {yes_price}% | **No:** {100-yes_price}%\n"
                      f"Volume: ${volume:,} | Resolves: {res_str}{pos_str}",
                inline=False
            )
        
        embed.set_footer(text=f"Use /trade [marketID] to trade • /market status [marketID] for details")
        
        await interaction.followup.send(embed=embed)
    
    @market_group.command(name="status", description="View detailed market status and order book")
    @app_commands.describe(market_id="The market ID (e.g., MKT001)")
    async def market_status(self, interaction: discord.Interaction, market_id: str):
        """View detailed market status including order book."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT question, yes_price, total_volume, resolution_week, status, created_by, created_at
            FROM prediction_markets
            WHERE market_id = ? AND guild_id = ?
        ''', (market_id.upper(), interaction.guild.id))
        
        market = cursor.fetchone()
        
        if not market:
            await interaction.followup.send(f"❌ Market `{market_id}` not found.", ephemeral=True)
            return
        
        question, yes_price, volume, res_week, status, creator_id, created_at = market
        
        # Get recent trades
        cursor.execute('''
            SELECT side, quantity, price, executed_at, buyer_id, seller_id
            FROM prediction_trades
            WHERE market_id = ?
            ORDER BY executed_at DESC
            LIMIT 5
        ''', (market_id.upper(),))
        recent_trades = cursor.fetchall()
        conn.close()
        
        # Get order book
        order_book = self._get_order_book(market_id.upper())
        
        embed = discord.Embed(
            title=f"📊 Market Status: {market_id.upper()}",
            description=f"**{question}**",
            color=discord.Color.green() if status == 'active' else discord.Color.red(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📈 Current Odds",
            value=f"**Yes:** {yes_price}¢ ({yes_price}%)\n**No:** {100-yes_price}¢ ({100-yes_price}%)",
            inline=True
        )
        
        embed.add_field(
            name="💰 Volume",
            value=f"${volume:,}",
            inline=True
        )
        
        embed.add_field(
            name="📅 Status",
            value=f"{status.title()}\nResolves: Week {res_week}" if res_week else f"{status.title()}\nManual resolution",
            inline=True
        )
        
        # Order book summary
        yes_bid = order_book['yes_bids'][0][3] if order_book['yes_bids'] else '-'
        yes_ask = order_book['yes_asks'][0][3] if order_book['yes_asks'] else '-'
        no_bid = order_book['no_bids'][0][3] if order_book['no_bids'] else '-'
        no_ask = order_book['no_asks'][0][3] if order_book['no_asks'] else '-'
        
        embed.add_field(
            name="📖 Order Book (Best Bid/Ask)",
            value=f"**Yes:** {yes_bid}¢ / {yes_ask}¢\n**No:** {no_bid}¢ / {no_ask}¢",
            inline=False
        )
        
        # Recent trades
        if recent_trades:
            trades_str = ""
            for side, qty, price, exec_at, buyer, seller in recent_trades[:5]:
                time_str = datetime.fromisoformat(exec_at).strftime("%m/%d %H:%M")
                trades_str += f"• {side} ${qty} @ {price}¢ ({time_str})\n"
            embed.add_field(name="🔄 Recent Trades", value=trades_str, inline=False)
        
        # User's position
        pnl = self._calculate_user_pnl(market_id.upper(), interaction.user.id, yes_price)
        if pnl['yes_shares'] > 0 or pnl['no_shares'] > 0:
            pnl_color = "🟢" if pnl['unrealized_pnl'] >= 0 else "🔴"
            embed.add_field(
                name="📍 Your Position",
                value=f"Yes: {pnl['yes_shares']} shares | No: {pnl['no_shares']} shares\n"
                      f"Invested: ${pnl['invested']:,} | Value: ${pnl['current_value']:,}\n"
                      f"{pnl_color} Unrealized P/L: ${pnl['unrealized_pnl']:+,}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="trade", description="Place a trade on a prediction market")
    @app_commands.describe(
        market_id="Market ID (e.g., MKT001)",
        side="Yes or No",
        direction="Buy or Sell",
        amount="Dollar amount ($10 increments)",
        limit_price="Max price for buy / Min price for sell (in cents, 5-95)"
    )
    @app_commands.choices(
        side=[
            app_commands.Choice(name="Yes", value="Yes"),
            app_commands.Choice(name="No", value="No")
        ],
        direction=[
            app_commands.Choice(name="Buy", value="buy"),
            app_commands.Choice(name="Sell", value="sell")
        ]
    )
    async def trade(
        self,
        interaction: discord.Interaction,
        market_id: str,
        side: str,
        direction: str,
        amount: int,
        limit_price: int
    ):
        """Place a trade on a prediction market."""
        await interaction.response.defer()
        
        market_id = market_id.upper()
        
        # Validate amount
        valid, error = self._validate_trade_amount(amount)
        if not valid:
            await interaction.followup.send(f"❌ {error}", ephemeral=True)
            return
        
        # Validate price
        if limit_price < MIN_PRICE or limit_price > MAX_PRICE:
            await interaction.followup.send(f"❌ Price must be between {MIN_PRICE}¢ and {MAX_PRICE}¢", ephemeral=True)
            return
        
        # Check market exists and is active
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT status, yes_price, question FROM prediction_markets
            WHERE market_id = ? AND guild_id = ?
        ''', (market_id, interaction.guild.id))
        
        market = cursor.fetchone()
        
        if not market:
            await interaction.followup.send(f"❌ Market `{market_id}` not found.", ephemeral=True)
            conn.close()
            return
        
        if market[0] != 'active':
            await interaction.followup.send(f"❌ Market `{market_id}` is not active.", ephemeral=True)
            conn.close()
            return
        
        current_price = market[1]
        question = market[2]
        
        # Check user's current position for volume cap
        position = self._get_user_position(market_id, interaction.user.id)
        current_shares = position['yes_shares'] if side == 'Yes' else position['no_shares']
        
        # Calculate quantity (shares) from dollar amount
        quantity = amount  # In this system, $1 = 1 share at the limit price
        
        if direction == 'buy' and current_shares + quantity > MAX_SHARES_PER_USER_PER_MARKET:
            await interaction.followup.send(
                f"❌ Volume cap exceeded. Max {MAX_SHARES_PER_USER_PER_MARKET} shares per user per market.\n"
                f"You have {current_shares} {side} shares.",
                ephemeral=True
            )
            conn.close()
            return
        
        if direction == 'sell' and quantity > current_shares:
            await interaction.followup.send(
                f"❌ Insufficient shares. You have {current_shares} {side} shares.",
                ephemeral=True
            )
            conn.close()
            return
        
        conn.close()
        
        # Try to match against existing orders
        match_result = self._match_order(market_id, interaction.user.id, side, direction, quantity, limit_price)
        
        filled = match_result['filled_quantity']
        remaining = match_result['remaining']
        
        # If not fully filled, bot fills the rest (guaranteed clear)
        bot_fill = None
        if remaining > 0:
            bot_fill = self._fill_with_bot(market_id, interaction.user.id, side, direction, remaining, limit_price)
            filled += bot_fill['filled_quantity']
        
        # Update market price
        self._update_market_price(market_id)
        
        # Get updated position
        new_position = self._get_user_position(market_id, interaction.user.id)
        
        # Create response embed
        embed = discord.Embed(
            title=f"✅ Trade Executed: {market_id}",
            description=f"**{question[:100]}**",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        total_cost = match_result['total_cost'] + (bot_fill['total_cost'] if bot_fill else 0)
        avg_price = total_cost // filled if filled > 0 else limit_price
        
        embed.add_field(
            name="📈 Order Details",
            value=f"**{direction.title()}** {side}\n"
                  f"Amount: ${amount}\n"
                  f"Filled: ${filled} @ avg {avg_price}¢",
            inline=True
        )
        
        embed.add_field(
            name="📍 Your Position",
            value=f"Yes: {new_position['yes_shares']} shares\n"
                  f"No: {new_position['no_shares']} shares",
            inline=True
        )
        
        # Check for big price move
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT yes_price FROM prediction_markets WHERE market_id = ?', (market_id,))
        new_price = cursor.fetchone()[0]
        conn.close()
        
        price_change = new_price - current_price
        if abs(price_change) >= 10:
            embed.add_field(
                name="🚨 Big Move!",
                value=f"Yes odds moved {price_change:+d}% ({current_price}% → {new_price}%)",
                inline=False
            )
            
            # Announce in channel
            channel = discord.utils.get(interaction.guild.text_channels, name='prediction-markets')
            if channel:
                alert_embed = discord.Embed(
                    title=f"🚨 Big Move in {market_id}!",
                    description=f"**{question[:100]}**\n\nYes odds: {current_price}% → **{new_price}%** ({price_change:+d}%)",
                    color=discord.Color.orange()
                )
                await channel.send(embed=alert_embed)
        
        embed.set_footer(text=f"6% fee on profits when market resolves")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="cancelorder", description="Cancel an open order")
    @app_commands.describe(order_id="The order ID to cancel")
    async def cancel_order(self, interaction: discord.Interaction, order_id: int):
        """Cancel an open order."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT market_id, side, direction, quantity, filled_quantity, price
            FROM prediction_orders
            WHERE order_id = ? AND user_id = ? AND status = 'open'
        ''', (order_id, interaction.user.id))
        
        order = cursor.fetchone()
        
        if not order:
            await interaction.response.send_message(
                "❌ Order not found or already filled/cancelled.",
                ephemeral=True
            )
            conn.close()
            return
        
        cursor.execute('''
            UPDATE prediction_orders SET status = 'cancelled' WHERE order_id = ?
        ''', (order_id,))
        
        conn.commit()
        conn.close()
        
        market_id, side, direction, qty, filled, price = order
        remaining = qty - filled
        
        await interaction.response.send_message(
            f"✅ Order #{order_id} cancelled.\n"
            f"Market: {market_id} | {direction.title()} {side} | "
            f"Cancelled: ${remaining} @ {price}¢ (${filled} was already filled)",
            ephemeral=True
        )
    
    @app_commands.command(name="mypositions", description="View your positions and P/L")
    async def my_positions(self, interaction: discord.Interaction):
        """View all your positions and unrealized P/L."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all positions
        cursor.execute('''
            SELECT p.market_id, p.yes_shares, p.no_shares, p.total_invested,
                   m.question, m.yes_price, m.status
            FROM prediction_positions p
            JOIN prediction_markets m ON p.market_id = m.market_id
            WHERE p.user_id = ? AND m.guild_id = ?
            AND (p.yes_shares > 0 OR p.no_shares > 0)
        ''', (interaction.user.id, interaction.guild.id))
        
        positions = cursor.fetchall()
        
        # Get open orders
        cursor.execute('''
            SELECT o.order_id, o.market_id, o.side, o.direction, 
                   o.quantity - o.filled_quantity as remaining, o.price
            FROM prediction_orders o
            JOIN prediction_markets m ON o.market_id = m.market_id
            WHERE o.user_id = ? AND o.status = 'open' AND m.guild_id = ?
            AND o.quantity > o.filled_quantity
        ''', (interaction.user.id, interaction.guild.id))
        
        open_orders = cursor.fetchall()
        
        # Get lifetime profits
        cursor.execute('''
            SELECT total_profit, total_volume, markets_won, markets_lost
            FROM prediction_profits
            WHERE user_id = ?
        ''', (interaction.user.id,))
        
        profits = cursor.fetchone()
        conn.close()
        
        embed = discord.Embed(
            title=f"📊 {interaction.user.display_name}'s Positions",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        total_invested = 0
        total_value = 0
        total_unrealized = 0
        
        if positions:
            for market_id, yes_shares, no_shares, invested, question, yes_price, status in positions:
                yes_value = yes_shares * yes_price
                no_value = no_shares * (100 - yes_price)
                current_value = yes_value + no_value
                unrealized = current_value - invested
                
                total_invested += invested
                total_value += current_value
                total_unrealized += unrealized
                
                pnl_emoji = "🟢" if unrealized >= 0 else "🔴"
                status_emoji = "🔴" if status != 'active' else ""
                
                embed.add_field(
                    name=f"{market_id}: {question[:40]}... {status_emoji}",
                    value=f"Yes: {yes_shares} | No: {no_shares}\n"
                          f"Invested: ${invested:,} | Value: ${current_value:,}\n"
                          f"{pnl_emoji} P/L: ${unrealized:+,}",
                    inline=False
                )
        else:
            embed.add_field(name="📭 No Positions", value="You don't have any open positions.", inline=False)
        
        # Open orders
        if open_orders:
            orders_str = ""
            for order_id, market_id, side, direction, remaining, price in open_orders:
                orders_str += f"• #{order_id}: {market_id} {direction.title()} {side} ${remaining} @ {price}¢\n"
            embed.add_field(name="📋 Open Orders", value=orders_str[:1024], inline=False)
        
        # Summary
        pnl_emoji = "🟢" if total_unrealized >= 0 else "🔴"
        embed.add_field(
            name="💰 Summary",
            value=f"Total Invested: ${total_invested:,}\n"
                  f"Current Value: ${total_value:,}\n"
                  f"{pnl_emoji} Unrealized P/L: ${total_unrealized:+,}",
            inline=True
        )
        
        # Lifetime stats
        if profits:
            total_profit, volume, won, lost = profits
            win_rate = (won / (won + lost) * 100) if (won + lost) > 0 else 0
            profit_emoji = "🟢" if total_profit >= 0 else "🔴"
            embed.add_field(
                name="🏆 Lifetime Stats",
                value=f"{profit_emoji} Settled P/L: ${total_profit:+,}\n"
                      f"Volume: ${volume:,}\n"
                      f"Record: {won}W-{lost}L ({win_rate:.0f}%)",
                inline=True
            )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="predictionleaderboard", description="View prediction market rankings")
    async def prediction_leaderboard(self, interaction: discord.Interaction):
        """View league rankings by net profits."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, total_profit, total_volume, markets_won, markets_lost
            FROM prediction_profits
            ORDER BY total_profit DESC
            LIMIT 15
        ''')
        
        rankings = cursor.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title="🏆 Prediction Market Leaderboard",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        if not rankings:
            embed.description = "No settled markets yet. Start trading!"
        else:
            leaderboard_str = ""
            for i, (user_id, profit, volume, won, lost) in enumerate(rankings, 1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                
                win_rate = (won / (won + lost) * 100) if (won + lost) > 0 else 0
                profit_emoji = "🟢" if profit >= 0 else "🔴"
                
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
                
                leaderboard_str += f"{medal} **{name}** {profit_emoji} ${profit:+,} ({win_rate:.0f}% win rate)\n"
            
            embed.description = leaderboard_str
        
        embed.set_footer(text="Rankings based on settled market profits (6% fee deducted)")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="resolvemarket", description="[Admin] Resolve a prediction market")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        market_id="Market ID to resolve",
        result="The outcome (Yes or No)"
    )
    @app_commands.choices(
        result=[
            app_commands.Choice(name="Yes", value="Yes"),
            app_commands.Choice(name="No", value="No")
        ]
    )
    async def resolve_market(self, interaction: discord.Interaction, market_id: str, result: str):
        """Resolve a market and settle all positions."""
        await interaction.response.defer()
        
        market_id = market_id.upper()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check market exists and is active
        cursor.execute('''
            SELECT question, status, channel_id FROM prediction_markets
            WHERE market_id = ? AND guild_id = ?
        ''', (market_id, interaction.guild.id))
        
        market = cursor.fetchone()
        
        if not market:
            await interaction.followup.send(f"❌ Market `{market_id}` not found.", ephemeral=True)
            conn.close()
            return
        
        if market[1] != 'active':
            await interaction.followup.send(f"❌ Market `{market_id}` is already resolved.", ephemeral=True)
            conn.close()
            return
        
        question, _, channel_id = market
        
        # Get all positions
        cursor.execute('''
            SELECT user_id, yes_shares, no_shares, total_invested
            FROM prediction_positions
            WHERE market_id = ?
        ''', (market_id,))
        
        positions = cursor.fetchall()
        
        # Calculate payouts
        payouts = []
        total_house_fee = 0
        
        for user_id, yes_shares, no_shares, invested in positions:
            if user_id == 0:  # Skip bot
                continue
            
            # Winning shares pay out $1 each (100 cents)
            if result == 'Yes':
                payout = yes_shares * 100  # Yes shares win
            else:
                payout = no_shares * 100  # No shares win
            
            profit = payout - invested
            
            # Apply house fee on profits only
            if profit > 0:
                fee = int(profit * HOUSE_FEE_RATE)
                total_house_fee += fee
                net_profit = profit - fee
            else:
                fee = 0
                net_profit = profit
            
            # Update user's lifetime stats
            cursor.execute('''
                INSERT INTO prediction_profits (user_id, total_profit, total_volume, markets_won, markets_lost, markets_participated)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    total_profit = total_profit + ?,
                    total_volume = total_volume + ?,
                    markets_won = markets_won + ?,
                    markets_lost = markets_lost + ?,
                    markets_participated = markets_participated + 1
            ''', (user_id, net_profit, invested, 1 if profit > 0 else 0, 1 if profit < 0 else 0,
                  net_profit, invested, 1 if profit > 0 else 0, 1 if profit < 0 else 0))
            
            if profit != 0:
                payouts.append({
                    'user_id': user_id,
                    'invested': invested,
                    'payout': payout,
                    'profit': profit,
                    'fee': fee,
                    'net_profit': net_profit
                })
        
        # Update house pot
        cursor.execute('''
            UPDATE prediction_house_pot 
            SET total_fees = total_fees + ?, last_updated = ?
            WHERE id = 1
        ''', (total_house_fee, datetime.now().isoformat()))
        
        # Mark market as resolved
        cursor.execute('''
            UPDATE prediction_markets 
            SET status = 'resolved', result = ?, resolved_at = ?
            WHERE market_id = ?
        ''', (result, datetime.now().isoformat(), market_id))
        
        conn.commit()
        conn.close()
        
        # Create resolution embed
        embed = discord.Embed(
            title=f"🏁 Market Resolved: {market_id}",
            description=f"**{question}**\n\n**Result: {result}** ✅",
            color=discord.Color.green() if result == 'Yes' else discord.Color.red(),
            timestamp=datetime.now()
        )
        
        # Show top winners/losers
        winners = sorted([p for p in payouts if p['net_profit'] > 0], key=lambda x: x['net_profit'], reverse=True)[:5]
        losers = sorted([p for p in payouts if p['net_profit'] < 0], key=lambda x: x['net_profit'])[:5]
        
        if winners:
            winners_str = ""
            for p in winners:
                member = interaction.guild.get_member(p['user_id'])
                name = member.display_name if member else f"User {p['user_id']}"
                winners_str += f"🟢 **{name}**: +${p['net_profit']:,} (fee: ${p['fee']})\n"
            embed.add_field(name="🏆 Winners", value=winners_str, inline=True)
        
        if losers:
            losers_str = ""
            for p in losers:
                member = interaction.guild.get_member(p['user_id'])
                name = member.display_name if member else f"User {p['user_id']}"
                losers_str += f"🔴 **{name}**: ${p['net_profit']:,}\n"
            embed.add_field(name="📉 Losers", value=losers_str, inline=True)
        
        embed.add_field(
            name="🏦 House Fee Collected",
            value=f"${total_house_fee:,}",
            inline=False
        )
        
        embed.set_footer(text=f"Resolved by {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed)
        
        # Also post to prediction-markets channel
        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed)
    
    @tasks.loop(hours=1)
    async def update_market_odds(self):
        """Periodically update market odds and check for auto-resolution."""
        logger.info("Running hourly market odds update...")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all active markets
        cursor.execute('''
            SELECT market_id, guild_id, resolution_week, channel_id
            FROM prediction_markets
            WHERE status = 'active'
        ''')
        
        markets = cursor.fetchall()
        conn.close()
        
        for market_id, guild_id, res_week, channel_id in markets:
            # Update price based on recent trades
            self._update_market_price(market_id)
            
            # Refresh bot liquidity if needed
            order_book = self._get_order_book(market_id)
            
            # Add more bot liquidity if order book is thin
            if len(order_book['yes_bids']) < 2 or len(order_book['yes_asks']) < 2:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('SELECT yes_price FROM prediction_markets WHERE market_id = ?', (market_id,))
                current_price = cursor.fetchone()[0]
                conn.close()
                
                self._seed_bot_liquidity(market_id, current_price)
    
    @update_market_odds.before_loop
    async def before_update_market_odds(self):
        """Wait for bot to be ready."""
        await self.bot.wait_until_ready()
    
    # ==================== NFC REQUIREMENT TRACKING ====================
    
    def _is_nfc_member(self, member: discord.Member) -> bool:
        """Check if a member is an NFC team owner."""
        for role in member.roles:
            role_name = role.name.upper()
            for nfc_team in NFC_TEAMS:
                if nfc_team.upper() in role_name or role_name in nfc_team.upper():
                    return True
        return False
    
    def _get_user_prediction_volume(self, user_id: int, guild_id: int) -> int:
        """Get total volume a user has traded in prediction markets."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Sum all trades (buys) for this user
        cursor.execute('''
            SELECT COALESCE(SUM(t.total_amount), 0)
            FROM prediction_trades t
            JOIN prediction_markets m ON t.market_id = m.market_id
            WHERE (t.buyer_id = ? OR t.seller_id = ?) AND m.guild_id = ?
        ''', (user_id, user_id, guild_id))
        
        volume = cursor.fetchone()[0]
        conn.close()
        
        return volume // 100  # Convert cents to dollars
    
    def _get_nfc_members_status(self, guild: discord.Guild) -> List[Dict]:
        """Get all NFC members and their prediction market status."""
        nfc_status = []
        
        for member in guild.members:
            if member.bot:
                continue
            
            if self._is_nfc_member(member):
                volume = self._get_user_prediction_volume(member.id, guild.id)
                remaining = max(0, NFC_MIN_VOLUME_REQUIREMENT - volume)
                
                nfc_status.append({
                    'user_id': member.id,
                    'name': member.display_name,
                    'volume': volume,
                    'remaining': remaining,
                    'met_requirement': volume >= NFC_MIN_VOLUME_REQUIREMENT
                })
        
        return nfc_status
    
    async def _get_current_week(self, guild_id: int) -> int:
        """Get current week from Snallabot."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT league_id FROM league_config WHERE guild_id = ? AND is_active = 1
            ''', (guild_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return 0
            
            league_id = row[0]
            
            async with aiohttp.ClientSession() as session:
                url = f"{SNALLABOT_API_BASE}/league/{league_id}/week"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('week', 0)
        except Exception as e:
            logger.error(f"Error getting current week: {e}")
        
        return 0
    
    @tasks.loop(hours=24)
    async def check_nfc_requirements(self):
        """Daily check for NFC prediction market requirements."""
        logger.info("Running daily NFC requirement check...")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all guilds with active markets
        cursor.execute('''
            SELECT DISTINCT guild_id FROM prediction_markets WHERE status = 'active'
        ''')
        
        guilds = cursor.fetchall()
        conn.close()
        
        for (guild_id,) in guilds:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            
            # Get current week
            current_week = await self._get_current_week(guild_id)
            
            # Only alert if we're approaching Week 18 deadline
            if current_week < 14:  # Start alerting from Week 14
                continue
            
            weeks_remaining = NFC_DEADLINE_WEEK - current_week
            
            # Get NFC members who haven't met requirement
            nfc_status = self._get_nfc_members_status(guild)
            non_compliant = [m for m in nfc_status if not m['met_requirement']]
            
            if not non_compliant:
                continue
            
            # Find prediction-markets or announcements channel
            channel = discord.utils.get(guild.text_channels, name='prediction-markets')
            if not channel:
                channel = discord.utils.get(guild.text_channels, name='announcements')
            if not channel:
                channel = discord.utils.get(guild.text_channels, name='townsquare')
            
            if not channel:
                continue
            
            # Create alert embed
            urgency = "🚨" if weeks_remaining <= 2 else "⚠️" if weeks_remaining <= 4 else "📢"
            color = discord.Color.red() if weeks_remaining <= 2 else discord.Color.orange() if weeks_remaining <= 4 else discord.Color.blue()
            
            embed = discord.Embed(
                title=f"{urgency} NFC Prediction Market Requirement Alert",
                description=f"**NFC members must place at least ${NFC_MIN_VOLUME_REQUIREMENT} in prediction markets by end of Week {NFC_DEADLINE_WEEK}!**\n\n"
                           f"Current Week: **{current_week}**\n"
                           f"Weeks Remaining: **{weeks_remaining}**",
                color=color,
                timestamp=datetime.now()
            )
            
            # List non-compliant members
            non_compliant_str = ""
            for m in sorted(non_compliant, key=lambda x: x['remaining'], reverse=True):
                non_compliant_str += f"• **{m['name']}**: ${m['volume']} traded (need ${m['remaining']} more)\n"
            
            embed.add_field(
                name=f"📋 NFC Members Below ${NFC_MIN_VOLUME_REQUIREMENT} ({len(non_compliant)})",
                value=non_compliant_str[:1024] if non_compliant_str else "All NFC members have met the requirement! 🎉",
                inline=False
            )
            
            embed.add_field(
                name="💡 How to Participate",
                value="1. View markets: `/market view`\n"
                      "2. Place a trade: `/trade [marketID] Yes buy 10 50`\n"
                      "3. Check your status: `/nfcstatus`",
                inline=False
            )
            
            embed.set_footer(text="Requirement: $100 minimum in prediction markets by Week 18")
            
            await channel.send(embed=embed)
            
            # DM members who are very behind (less than 50% and within 4 weeks)
            if weeks_remaining <= 4:
                for m in non_compliant:
                    if m['volume'] < NFC_MIN_VOLUME_REQUIREMENT / 2:
                        member = guild.get_member(m['user_id'])
                        if member:
                            try:
                                dm_embed = discord.Embed(
                                    title=f"{urgency} Prediction Market Requirement Reminder",
                                    description=f"Hi {member.display_name}!\n\n"
                                               f"As an NFC team owner, you need to place at least **${NFC_MIN_VOLUME_REQUIREMENT}** in prediction markets by **Week {NFC_DEADLINE_WEEK}**.\n\n"
                                               f"**Your current volume:** ${m['volume']}\n"
                                               f"**Still needed:** ${m['remaining']}\n"
                                               f"**Weeks remaining:** {weeks_remaining}",
                                    color=color
                                )
                                dm_embed.add_field(
                                    name="Quick Start",
                                    value="Use `/market view` to see available markets, then `/trade` to participate!",
                                    inline=False
                                )
                                await member.send(embed=dm_embed)
                            except discord.Forbidden:
                                pass  # Can't DM this user
    
    @check_nfc_requirements.before_loop
    async def before_check_nfc_requirements(self):
        """Wait for bot to be ready."""
        await self.bot.wait_until_ready()
    
    @app_commands.command(name="nfcstatus", description="Check NFC prediction market requirement status")
    async def nfc_status(self, interaction: discord.Interaction):
        """Check NFC members' prediction market requirement status."""
        await interaction.response.defer()
        
        nfc_status = self._get_nfc_members_status(interaction.guild)
        
        if not nfc_status:
            await interaction.followup.send("No NFC team owners found.", ephemeral=True)
            return
        
        current_week = await self._get_current_week(interaction.guild.id)
        weeks_remaining = max(0, NFC_DEADLINE_WEEK - current_week)
        
        # Separate compliant and non-compliant
        compliant = [m for m in nfc_status if m['met_requirement']]
        non_compliant = sorted([m for m in nfc_status if not m['met_requirement']], 
                               key=lambda x: x['remaining'], reverse=True)
        
        embed = discord.Embed(
            title="📊 NFC Prediction Market Requirement Status",
            description=f"**Requirement:** ${NFC_MIN_VOLUME_REQUIREMENT} minimum by Week {NFC_DEADLINE_WEEK}\n"
                       f"**Current Week:** {current_week} | **Weeks Remaining:** {weeks_remaining}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Compliant members
        if compliant:
            compliant_str = "\n".join([f"✅ **{m['name']}**: ${m['volume']}" for m in compliant[:10]])
            if len(compliant) > 10:
                compliant_str += f"\n... and {len(compliant) - 10} more"
            embed.add_field(name=f"✅ Met Requirement ({len(compliant)})", value=compliant_str, inline=False)
        
        # Non-compliant members
        if non_compliant:
            non_compliant_str = "\n".join([f"❌ **{m['name']}**: ${m['volume']} (need ${m['remaining']} more)" 
                                           for m in non_compliant[:10]])
            if len(non_compliant) > 10:
                non_compliant_str += f"\n... and {len(non_compliant) - 10} more"
            embed.add_field(name=f"❌ Below Requirement ({len(non_compliant)})", value=non_compliant_str, inline=False)
        
        # Check if user is NFC and show their status
        user_status = next((m for m in nfc_status if m['user_id'] == interaction.user.id), None)
        if user_status:
            status_emoji = "✅" if user_status['met_requirement'] else "❌"
            remaining_text = 'Requirement met! 🎉' if user_status['met_requirement'] else f"Need ${user_status['remaining']} more"
            embed.add_field(
                name="📍 Your Status",
                value=f"{status_emoji} Volume: ${user_status['volume']} / ${NFC_MIN_VOLUME_REQUIREMENT}\n{remaining_text}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(PredictionMarketsCog(bot))
