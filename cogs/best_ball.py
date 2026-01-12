"""
Best Ball Fantasy Football Cog
Features:
- Create and manage Best Ball events
- Roster building with player selection
- Automatic weekly lineup optimization
- PPR scoring based on Madden sim stats
- Loser-pays-winner payout system (bottom pays top)
- Integration with wager/payment tracking
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import aiohttp
import re

logger = logging.getLogger('MistressLIV.BestBall')

# Scoring constants (PPR)
SCORING = {
    'passing_yards': 0.04,
    'passing_td': 4,
    'interception': -2,
    'rushing_yards': 0.1,
    'rushing_td': 6,
    'receiving_yards': 0.1,
    'receiving_td': 6,
    'reception': 1,  # PPR
    'two_pt_conversion': 2,
    'bonus_40_yard_td': 3,
    'bonus_100_yard_game': 5,
    # DST scoring
    'dst_shutout': 10,
    'dst_sack': 1,
    'dst_interception': 2,
    'dst_fumble_recovery': 2,
    'dst_td': 6,
    'dst_yards_allowed_per': -0.05,
}

# Roster requirements
ROSTER_SIZE = 20
MIN_ROSTER = {
    'QB': 1,
    'RB': 2,
    'WR': 3,
    'TE': 1,
    'DST': 0
}
MAX_ROSTER = {
    'QB': 2,
    'RB': 6,
    'WR': 7,
    'TE': 3,
    'DST': 2
}

# Starting lineup
STARTING_LINEUP = {
    'QB': 1,
    'RB': 2,
    'WR': 3,
    'TE': 1,
    'FLEX': 2,  # RB/WR/TE
    'DST': 1
}


class BestBallCog(commands.Cog):
    """Cog for Best Ball fantasy football management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = bot.db_path
        self._ensure_tables()
        self.active_roster_builds = {}  # Track users building rosters
        
    def get_db_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def _ensure_tables(self):
        """Create all required tables for Best Ball."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Best Ball Events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_events (
                event_id TEXT PRIMARY KEY,
                creator_id INTEGER NOT NULL,
                entry_fee REAL DEFAULT 0,
                duration_weeks INTEGER DEFAULT 17,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                season INTEGER,
                current_week INTEGER DEFAULT 0
            )
        ''')
        
        # Participants table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                total_points REAL DEFAULT 0,
                total_bench_points REAL DEFAULT 0,
                total_tds INTEGER DEFAULT 0,
                final_rank INTEGER,
                FOREIGN KEY (event_id) REFERENCES bestball_events(event_id),
                UNIQUE(event_id, user_id)
            )
        ''')
        
        # Rosters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_rosters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                position TEXT NOT NULL,
                team TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES bestball_events(event_id),
                UNIQUE(event_id, user_id, player_id)
            )
        ''')
        
        # Weekly scores table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_weekly_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                points REAL DEFAULT 0,
                is_starter INTEGER DEFAULT 0,
                lineup_position TEXT,
                FOREIGN KEY (event_id) REFERENCES bestball_events(event_id),
                UNIQUE(event_id, user_id, week, player_id)
            )
        ''')
        
        # Best Ball payments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bestball_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                payer_id INTEGER NOT NULL,
                payee_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payer_rank INTEGER,
                payee_rank INTEGER,
                is_paid INTEGER DEFAULT 0,
                paid_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES bestball_events(event_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Best Ball tables initialized")
    
    def _generate_event_id(self, season: int = None) -> str:
        """Generate a unique event ID."""
        if season is None:
            season = datetime.now().year
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM bestball_events 
            WHERE event_id LIKE ?
        ''', (f'BB-SZN{season}-%',))
        count = cursor.fetchone()[0]
        conn.close()
        
        return f"BB-SZN{season}-{count + 1:03d}"
    
    async def _get_player_pool(self) -> List[Dict]:
        """Get all available players from Madden export data."""
        # Try to get from Snallabot/export data
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check for cached player data
        cursor.execute('''
            SELECT data FROM snallabot_cache 
            WHERE cache_key = 'player_roster' 
            ORDER BY updated_at DESC LIMIT 1
        ''')
        result = cursor.fetchone()
        conn.close()
        
        if result:
            try:
                return json.loads(result[0])
            except:
                pass
        
        # Fallback: try to fetch from Snallabot
        try:
            async with aiohttp.ClientSession() as session:
                # Get league ID from config
                conn = self.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM bot_config WHERE key = 'snallabot_league_id'")
                result = cursor.fetchone()
                conn.close()
                
                league_id = result[0] if result else 'liv'
                
                url = f"https://snallabot-event-sender-b869b2ccfed0.herokuapp.com/dashboard/{league_id}/export"
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'rosters' in data:
                            return data['rosters']
        except Exception as e:
            logger.error(f"Error fetching player pool: {e}")
        
        return []
    
    def _search_players(self, query: str, players: List[Dict], position: str = None) -> List[Dict]:
        """Fuzzy search for players by name."""
        query_lower = query.lower()
        matches = []
        
        for player in players:
            name = player.get('firstName', '') + ' ' + player.get('lastName', '')
            name_lower = name.lower()
            
            # Check position filter
            if position and player.get('position', '').upper() != position.upper():
                continue
            
            # Check for match
            if query_lower in name_lower or name_lower.startswith(query_lower):
                matches.append({
                    'id': player.get('rosterId') or player.get('playerId'),
                    'name': name.strip(),
                    'position': player.get('position', 'UNK'),
                    'team': player.get('teamId', 'FA'),
                    'overall': player.get('playerBestOvr') or player.get('overall', 0)
                })
        
        # Sort by overall rating
        matches.sort(key=lambda x: x.get('overall', 0), reverse=True)
        return matches[:10]  # Return top 10 matches
    
    def _calculate_player_score(self, stats: Dict) -> float:
        """Calculate fantasy points for a player based on their stats."""
        points = 0.0
        
        # Passing
        points += stats.get('passYds', 0) * SCORING['passing_yards']
        points += stats.get('passTDs', 0) * SCORING['passing_td']
        points += stats.get('passInts', 0) * SCORING['interception']
        
        # Rushing
        points += stats.get('rushYds', 0) * SCORING['rushing_yards']
        points += stats.get('rushTDs', 0) * SCORING['rushing_td']
        
        # Receiving
        points += stats.get('recYds', 0) * SCORING['receiving_yards']
        points += stats.get('recTDs', 0) * SCORING['receiving_td']
        points += stats.get('receptions', 0) * SCORING['reception']
        
        # Bonuses
        if stats.get('rushYds', 0) >= 100 or stats.get('recYds', 0) >= 100 or stats.get('passYds', 0) >= 300:
            points += SCORING['bonus_100_yard_game']
        
        return round(points, 2)
    
    def _optimize_lineup(self, roster_scores: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Optimize lineup by selecting best players for each position.
        Returns (starters, bench)
        """
        # Group by position
        by_position = {'QB': [], 'RB': [], 'WR': [], 'TE': [], 'DST': []}
        for player in roster_scores:
            pos = player['position'].upper()
            if pos in by_position:
                by_position[pos].append(player)
            elif pos in ['HB', 'FB']:
                by_position['RB'].append(player)
            elif pos == 'K':
                continue  # Skip kickers
        
        # Sort each position by points
        for pos in by_position:
            by_position[pos].sort(key=lambda x: x['points'], reverse=True)
        
        starters = []
        used_players = set()
        
        # Fill required positions
        for pos, count in [('QB', 1), ('RB', 2), ('WR', 3), ('TE', 1), ('DST', 1)]:
            for i in range(count):
                if by_position[pos]:
                    player = by_position[pos].pop(0)
                    player['lineup_position'] = pos
                    starters.append(player)
                    used_players.add(player['player_id'])
        
        # Fill FLEX spots (best remaining RB/WR/TE)
        flex_pool = by_position['RB'] + by_position['WR'] + by_position['TE']
        flex_pool.sort(key=lambda x: x['points'], reverse=True)
        
        for i in range(2):  # 2 FLEX spots
            if flex_pool:
                player = flex_pool.pop(0)
                player['lineup_position'] = 'FLEX'
                starters.append(player)
                used_players.add(player['player_id'])
        
        # Remaining players are bench
        bench = [p for p in roster_scores if p['player_id'] not in used_players]
        
        return starters, bench
    
    def _generate_payments(self, event_id: str) -> List[Dict]:
        """
        Generate loser-pays-winner payments for a completed event.
        Bottom finisher pays top finisher, 2nd bottom pays 2nd place, etc.
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get event info
        cursor.execute('SELECT entry_fee FROM bestball_events WHERE event_id = ?', (event_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return []
        
        entry_fee = result[0]
        
        # Get final rankings
        cursor.execute('''
            SELECT user_id, total_points, total_bench_points, total_tds
            FROM bestball_participants
            WHERE event_id = ?
            ORDER BY total_points DESC, total_bench_points DESC, total_tds DESC
        ''', (event_id,))
        rankings = cursor.fetchall()
        
        if len(rankings) < 2:
            conn.close()
            return []
        
        # Update final ranks
        for rank, (user_id, _, _, _) in enumerate(rankings, 1):
            cursor.execute('''
                UPDATE bestball_participants 
                SET final_rank = ? 
                WHERE event_id = ? AND user_id = ?
            ''', (rank, event_id, user_id))
        
        # Generate payments: bottom half pays top half
        payments = []
        num_participants = len(rankings)
        num_payers = num_participants // 2
        
        for i in range(num_payers):
            winner_rank = i + 1
            loser_rank = num_participants - i
            
            winner_id = rankings[winner_rank - 1][0]
            loser_id = rankings[loser_rank - 1][0]
            
            # Insert payment record
            cursor.execute('''
                INSERT INTO bestball_payments 
                (event_id, payer_id, payee_id, amount, payer_rank, payee_rank)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (event_id, loser_id, winner_id, entry_fee, loser_rank, winner_rank))
            
            payments.append({
                'payer_id': loser_id,
                'payee_id': winner_id,
                'amount': entry_fee,
                'payer_rank': loser_rank,
                'payee_rank': winner_rank
            })
        
        conn.commit()
        conn.close()
        
        return payments
    
    # ==================== COMMANDS ====================
    
    @app_commands.command(name="startbestball", description="Start a new Best Ball event")
    @app_commands.describe(
        entry_fee="Entry fee amount (default: $50)",
        duration_weeks="Number of weeks to run (default: 17)"
    )
    async def start_best_ball(
        self,
        interaction: discord.Interaction,
        entry_fee: Optional[float] = 50.0,
        duration_weeks: Optional[int] = 17
    ):
        """Create a new Best Ball event."""
        await interaction.response.defer()
        
        event_id = self._generate_event_id()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bestball_events 
            (event_id, creator_id, entry_fee, duration_weeks, status, season)
            VALUES (?, ?, ?, ?, 'open', ?)
        ''', (event_id, interaction.user.id, entry_fee, duration_weeks, datetime.now().year))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🏈 New Best Ball Event Started!",
            description=f"**Event ID:** `{event_id}`",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="💰 Entry Fee", value=f"${entry_fee:.2f}", inline=True)
        embed.add_field(name="📅 Duration", value=f"{duration_weeks} weeks", inline=True)
        embed.add_field(name="📊 Status", value="Open for joins", inline=True)
        
        embed.add_field(
            name="📋 How to Join",
            value=f"Use `/joinbestball {event_id}` to join!\n1 entry per person.",
            inline=False
        )
        
        embed.add_field(
            name="💸 Payout Structure",
            value=(
                "**Losers pay Winners (bottom-up):**\n"
                "• Last place pays 1st place\n"
                "• 2nd to last pays 2nd place\n"
                "• And so on...\n"
                f"Each loser pays ${entry_fee:.2f} to their paired winner"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Created by {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed)
        
        # Also post to #best-ball channel if it exists
        best_ball_channel = discord.utils.get(interaction.guild.channels, name='best-ball')
        if best_ball_channel:
            await best_ball_channel.send(
                f"@everyone New Best Ball event started by {interaction.user.mention}!",
                embed=embed
            )
    
    @app_commands.command(name="joinbestball", description="Join a Best Ball event")
    @app_commands.describe(event_id="The event ID to join")
    async def join_best_ball(self, interaction: discord.Interaction, event_id: str):
        """Join an existing Best Ball event."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check event exists and is open
        cursor.execute('''
            SELECT status, entry_fee FROM bestball_events WHERE event_id = ?
        ''', (event_id,))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                f"❌ Event `{event_id}` not found.", ephemeral=True
            )
            conn.close()
            return
        
        status, entry_fee = result
        
        if status != 'open':
            await interaction.response.send_message(
                f"❌ Event `{event_id}` is no longer accepting participants (Status: {status}).",
                ephemeral=True
            )
            conn.close()
            return
        
        # Check if already joined
        cursor.execute('''
            SELECT id FROM bestball_participants 
            WHERE event_id = ? AND user_id = ?
        ''', (event_id, interaction.user.id))
        
        if cursor.fetchone():
            await interaction.response.send_message(
                "❌ You already have an entry in this event.", ephemeral=True
            )
            conn.close()
            return
        
        # Add participant
        cursor.execute('''
            INSERT INTO bestball_participants (event_id, user_id)
            VALUES (?, ?)
        ''', (event_id, interaction.user.id))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Joined Best Ball Event!",
            description=f"**Event ID:** `{event_id}`",
            color=discord.Color.green()
        )
        
        embed.add_field(name="💰 Entry Fee", value=f"${entry_fee:.2f}", inline=True)
        embed.add_field(
            name="📋 Next Step",
            value=f"Build your roster with `/selectyourteam {event_id}`",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="selectyourteam", description="Build your Best Ball roster")
    @app_commands.describe(event_id="The event ID to build roster for")
    async def select_your_team(self, interaction: discord.Interaction, event_id: str):
        """Interactive roster building."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Verify participation
        cursor.execute('''
            SELECT p.id, e.status FROM bestball_participants p
            JOIN bestball_events e ON p.event_id = e.event_id
            WHERE p.event_id = ? AND p.user_id = ?
        ''', (event_id, interaction.user.id))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                f"❌ You haven't joined event `{event_id}`. Use `/joinbestball {event_id}` first.",
                ephemeral=True
            )
            conn.close()
            return
        
        _, status = result
        if status != 'open':
            await interaction.response.send_message(
                "❌ This event is closed. Rosters can no longer be modified.",
                ephemeral=True
            )
            conn.close()
            return
        
        # Check current roster
        cursor.execute('''
            SELECT COUNT(*) FROM bestball_rosters
            WHERE event_id = ? AND user_id = ?
        ''', (event_id, interaction.user.id))
        roster_count = cursor.fetchone()[0]
        conn.close()
        
        if roster_count >= ROSTER_SIZE:
            await interaction.response.send_message(
                f"✅ Your roster is complete ({roster_count}/{ROSTER_SIZE} players).\n"
                f"Use `/reviewbestballroster {event_id}` to view it.",
                ephemeral=True
            )
            return
        
        # Start roster building view
        view = RosterBuildView(self, interaction.user.id, event_id, roster_count)
        
        embed = discord.Embed(
            title=f"🏈 Build Your Best Ball Roster",
            description=f"**Event:** `{event_id}`\n**Progress:** {roster_count}/{ROSTER_SIZE} players",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 Roster Requirements",
            value=(
                f"• QB: {MIN_ROSTER['QB']}-{MAX_ROSTER['QB']}\n"
                f"• RB: {MIN_ROSTER['RB']}-{MAX_ROSTER['RB']}\n"
                f"• WR: {MIN_ROSTER['WR']}-{MAX_ROSTER['WR']}\n"
                f"• TE: {MIN_ROSTER['TE']}-{MAX_ROSTER['TE']}\n"
                f"• DST: 0-{MAX_ROSTER['DST']}\n"
                f"• Total: {ROSTER_SIZE} players"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 Select Position",
            value="Choose a position below to add a player:",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="addplayer", description="Add a player to your Best Ball roster")
    @app_commands.describe(
        event_id="The event ID",
        position="Player position (QB, RB, WR, TE, DST)",
        player_name="Player name to search for"
    )
    async def add_player(
        self,
        interaction: discord.Interaction,
        event_id: str,
        position: str,
        player_name: str
    ):
        """Add a player to roster by name search."""
        await interaction.response.defer(ephemeral=True)
        
        position = position.upper()
        if position not in ['QB', 'RB', 'WR', 'TE', 'DST', 'FLEX']:
            await interaction.followup.send(
                "❌ Invalid position. Use QB, RB, WR, TE, or DST.",
                ephemeral=True
            )
            return
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Verify participation and event status
        cursor.execute('''
            SELECT e.status FROM bestball_participants p
            JOIN bestball_events e ON p.event_id = e.event_id
            WHERE p.event_id = ? AND p.user_id = ?
        ''', (event_id, interaction.user.id))
        result = cursor.fetchone()
        
        if not result:
            await interaction.followup.send(
                f"❌ You haven't joined event `{event_id}`.",
                ephemeral=True
            )
            conn.close()
            return
        
        if result[0] != 'open':
            await interaction.followup.send(
                "❌ This event is closed. Rosters cannot be modified.",
                ephemeral=True
            )
            conn.close()
            return
        
        # Check roster count
        cursor.execute('''
            SELECT COUNT(*) FROM bestball_rosters
            WHERE event_id = ? AND user_id = ?
        ''', (event_id, interaction.user.id))
        roster_count = cursor.fetchone()[0]
        
        if roster_count >= ROSTER_SIZE:
            await interaction.followup.send(
                f"❌ Your roster is full ({ROSTER_SIZE} players).",
                ephemeral=True
            )
            conn.close()
            return
        
        # Check position limits
        cursor.execute('''
            SELECT COUNT(*) FROM bestball_rosters
            WHERE event_id = ? AND user_id = ? AND position = ?
        ''', (event_id, interaction.user.id, position))
        pos_count = cursor.fetchone()[0]
        
        if position in MAX_ROSTER and pos_count >= MAX_ROSTER[position]:
            await interaction.followup.send(
                f"❌ You already have {pos_count} {position}s (max: {MAX_ROSTER[position]}).",
                ephemeral=True
            )
            conn.close()
            return
        
        conn.close()
        
        # Search for player
        players = await self._get_player_pool()
        search_pos = None if position == 'FLEX' else position
        matches = self._search_players(player_name, players, search_pos)
        
        if not matches:
            await interaction.followup.send(
                f"❌ No players found matching '{player_name}' at {position}.",
                ephemeral=True
            )
            return
        
        if len(matches) == 1:
            # Auto-add single match
            player = matches[0]
            success = await self._add_player_to_roster(
                event_id, interaction.user.id, player
            )
            
            if success:
                await interaction.followup.send(
                    f"✅ Added **{player['name']}** ({player['position']} - {player['team']}) to your roster!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Failed to add player. They may already be on your roster.",
                    ephemeral=True
                )
        else:
            # Show selection view
            view = PlayerSelectView(self, event_id, interaction.user.id, matches)
            
            embed = discord.Embed(
                title=f"🔍 Select Player",
                description=f"Multiple matches for '{player_name}':",
                color=discord.Color.blue()
            )
            
            for i, p in enumerate(matches, 1):
                embed.add_field(
                    name=f"{i}. {p['name']}",
                    value=f"{p['position']} - {p['team']} ({p['overall']} OVR)",
                    inline=True
                )
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def _add_player_to_roster(
        self,
        event_id: str,
        user_id: int,
        player: Dict
    ) -> bool:
        """Add a player to a user's roster."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO bestball_rosters 
                (event_id, user_id, player_id, player_name, position, team)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                event_id, user_id, player['id'], player['name'],
                player['position'], player['team']
            ))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    @app_commands.command(name="reviewbestballroster", description="View a Best Ball roster")
    @app_commands.describe(
        event_id="The event ID",
        user="User to view (leave blank for your own)"
    )
    async def review_roster(
        self,
        interaction: discord.Interaction,
        event_id: str,
        user: Optional[discord.Member] = None
    ):
        """View a participant's roster."""
        target_user = user or interaction.user
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get roster
        cursor.execute('''
            SELECT player_name, position, team
            FROM bestball_rosters
            WHERE event_id = ? AND user_id = ?
            ORDER BY 
                CASE position 
                    WHEN 'QB' THEN 1 
                    WHEN 'RB' THEN 2 
                    WHEN 'WR' THEN 3 
                    WHEN 'TE' THEN 4 
                    WHEN 'DST' THEN 5 
                    ELSE 6 
                END,
                player_name
        ''', (event_id, target_user.id))
        roster = cursor.fetchall()
        conn.close()
        
        if not roster:
            await interaction.response.send_message(
                f"❌ No roster found for {target_user.display_name} in event `{event_id}`.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🏈 {target_user.display_name}'s Best Ball Roster",
            description=f"**Event:** `{event_id}`\n**Players:** {len(roster)}/{ROSTER_SIZE}",
            color=discord.Color.blue()
        )
        
        # Group by position
        by_pos = {}
        for name, pos, team in roster:
            if pos not in by_pos:
                by_pos[pos] = []
            by_pos[pos].append(f"{name} ({team})")
        
        for pos in ['QB', 'RB', 'WR', 'TE', 'DST']:
            if pos in by_pos:
                embed.add_field(
                    name=f"**{pos}** ({len(by_pos[pos])})",
                    value="\n".join(by_pos[pos]),
                    inline=True
                )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="bestballstatus", description="Check Best Ball event status")
    @app_commands.describe(event_id="Event ID (leave blank for latest)")
    async def best_ball_status(
        self,
        interaction: discord.Interaction,
        event_id: Optional[str] = None
    ):
        """Show event status and leaderboard."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Get event
        if event_id:
            cursor.execute('''
                SELECT event_id, creator_id, entry_fee, duration_weeks, status, current_week
                FROM bestball_events WHERE event_id = ?
            ''', (event_id,))
        else:
            cursor.execute('''
                SELECT event_id, creator_id, entry_fee, duration_weeks, status, current_week
                FROM bestball_events 
                ORDER BY created_at DESC LIMIT 1
            ''')
        
        event = cursor.fetchone()
        
        if not event:
            await interaction.response.send_message(
                "❌ No Best Ball events found.",
                ephemeral=True
            )
            conn.close()
            return
        
        event_id, creator_id, entry_fee, duration_weeks, status, current_week = event
        
        # Get participants
        cursor.execute('''
            SELECT user_id, total_points, total_bench_points
            FROM bestball_participants
            WHERE event_id = ?
            ORDER BY total_points DESC, total_bench_points DESC
            LIMIT 10
        ''', (event_id,))
        participants = cursor.fetchall()
        
        cursor.execute('''
            SELECT COUNT(*) FROM bestball_participants WHERE event_id = ?
        ''', (event_id,))
        total_participants = cursor.fetchone()[0]
        
        conn.close()
        
        creator = interaction.guild.get_member(creator_id)
        creator_name = creator.display_name if creator else "Unknown"
        
        embed = discord.Embed(
            title=f"🏈 Best Ball Event: {event_id}",
            color=discord.Color.gold() if status == 'open' else discord.Color.blue()
        )
        
        embed.add_field(name="👤 Creator", value=creator_name, inline=True)
        embed.add_field(name="💰 Entry Fee", value=f"${entry_fee:.2f}", inline=True)
        embed.add_field(name="📊 Status", value=status.title(), inline=True)
        embed.add_field(name="👥 Participants", value=str(total_participants), inline=True)
        embed.add_field(name="📅 Week", value=f"{current_week}/{duration_weeks}", inline=True)
        embed.add_field(
            name="💸 Total Pot",
            value=f"${entry_fee * total_participants:.2f}",
            inline=True
        )
        
        if participants and current_week > 0:
            leaderboard = []
            for i, (user_id, points, bench_pts) in enumerate(participants[:5], 1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                leaderboard.append(f"**{i}.** {name}: {points:.1f} pts")
            
            embed.add_field(
                name="🏆 Top 5 Leaderboard",
                value="\n".join(leaderboard) if leaderboard else "No scores yet",
                inline=False
            )
        
        # Check if user is in event
        for user_id, points, _ in participants:
            if user_id == interaction.user.id:
                embed.add_field(
                    name="📊 Your Score",
                    value=f"{points:.1f} points",
                    inline=False
                )
                break
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="closebestball", description="[Admin] Close a Best Ball event")
    @app_commands.describe(event_id="Event ID to close")
    async def close_best_ball(self, interaction: discord.Interaction, event_id: str):
        """Close an event and lock rosters."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check if user is creator or admin
        cursor.execute('''
            SELECT creator_id, status FROM bestball_events WHERE event_id = ?
        ''', (event_id,))
        result = cursor.fetchone()
        
        if not result:
            await interaction.response.send_message(
                f"❌ Event `{event_id}` not found.",
                ephemeral=True
            )
            conn.close()
            return
        
        creator_id, status = result
        
        if interaction.user.id != creator_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only the event creator or admins can close events.",
                ephemeral=True
            )
            conn.close()
            return
        
        if status != 'open':
            await interaction.response.send_message(
                f"❌ Event is already {status}.",
                ephemeral=True
            )
            conn.close()
            return
        
        # Close event
        cursor.execute('''
            UPDATE bestball_events 
            SET status = 'active', closed_at = ?
            WHERE event_id = ?
        ''', (datetime.now().isoformat(), event_id))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ Event `{event_id}` is now closed. Rosters are locked and scoring will begin!"
        )
    
    @app_commands.command(name="endbestball", description="[Admin] End a Best Ball event and generate payments")
    @app_commands.describe(event_id="Event ID to end")
    async def end_best_ball(self, interaction: discord.Interaction, event_id: str):
        """End an event and generate payment obligations."""
        await interaction.response.defer()
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Check permissions
        cursor.execute('''
            SELECT creator_id, status, entry_fee FROM bestball_events WHERE event_id = ?
        ''', (event_id,))
        result = cursor.fetchone()
        
        if not result:
            await interaction.followup.send(f"❌ Event `{event_id}` not found.")
            conn.close()
            return
        
        creator_id, status, entry_fee = result
        
        if interaction.user.id != creator_id and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Only the event creator or admins can end events.")
            conn.close()
            return
        
        conn.close()
        
        # Generate payments
        payments = self._generate_payments(event_id)
        
        # Update event status
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE bestball_events SET status = 'completed' WHERE event_id = ?
        ''', (event_id,))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title=f"🏆 Best Ball Event Complete: {event_id}",
            description="Final standings and payment obligations generated!",
            color=discord.Color.gold()
        )
        
        # Show final standings
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, total_points, final_rank
            FROM bestball_participants
            WHERE event_id = ?
            ORDER BY final_rank
        ''', (event_id,))
        standings = cursor.fetchall()
        conn.close()
        
        standings_text = []
        for user_id, points, rank in standings[:10]:
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            standings_text.append(f"**{rank}.** {name}: {points:.1f} pts")
        
        embed.add_field(
            name="📊 Final Standings",
            value="\n".join(standings_text) if standings_text else "No participants",
            inline=False
        )
        
        # Show payments
        if payments:
            payment_text = []
            for p in payments[:10]:
                payer = interaction.guild.get_member(p['payer_id'])
                payee = interaction.guild.get_member(p['payee_id'])
                payer_name = payer.display_name if payer else f"User {p['payer_id']}"
                payee_name = payee.display_name if payee else f"User {p['payee_id']}"
                payment_text.append(
                    f"#{p['payer_rank']} {payer_name} → #{p['payee_rank']} {payee_name}: ${p['amount']:.2f}"
                )
            
            embed.add_field(
                name="💸 Payment Obligations (Loser → Winner)",
                value="\n".join(payment_text) if payment_text else "None",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
        
        # Post to #best-ball channel
        best_ball_channel = discord.utils.get(interaction.guild.channels, name='best-ball')
        if best_ball_channel:
            await best_ball_channel.send(embed=embed)
    
    @app_commands.command(name="bestballhelp", description="Show Best Ball rules and commands")
    async def best_ball_help(self, interaction: discord.Interaction):
        """Display help information for Best Ball."""
        embed = discord.Embed(
            title="🏈 Best Ball Fantasy Football",
            description="Low-maintenance fantasy where the bot auto-optimizes your lineup!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 Overview",
            value=(
                "• Build a 20-player roster at the start\n"
                "• No weekly management - bot picks best lineup\n"
                "• PPR scoring based on Madden sim stats\n"
                "• Highest total points wins!"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👥 Roster Requirements",
            value=(
                f"• **QB:** {MIN_ROSTER['QB']}-{MAX_ROSTER['QB']}\n"
                f"• **RB:** {MIN_ROSTER['RB']}-{MAX_ROSTER['RB']}\n"
                f"• **WR:** {MIN_ROSTER['WR']}-{MAX_ROSTER['WR']}\n"
                f"• **TE:** {MIN_ROSTER['TE']}-{MAX_ROSTER['TE']}\n"
                f"• **DST:** 0-{MAX_ROSTER['DST']}\n"
                f"• **Total:** {ROSTER_SIZE} players"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎯 Weekly Starters",
            value=(
                "• 1 QB\n"
                "• 2 RB\n"
                "• 3 WR\n"
                "• 1 TE\n"
                "• 2 FLEX (RB/WR/TE)\n"
                "• 1 DST"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📊 Scoring (PPR)",
            value=(
                "**Passing:** 0.04/yd, 4/TD, -2/INT\n"
                "**Rush/Rec:** 0.1/yd, 6/TD, 1/rec\n"
                "**Bonus:** +5 for 100+ yd game, +3 for 40+ yd TD"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💸 Payout Structure",
            value=(
                "**Losers pay Winners (bottom-up):**\n"
                "• Last place pays 1st place\n"
                "• 2nd to last pays 2nd place\n"
                "• And so on..."
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔧 Commands",
            value=(
                "`/startbestball` - Create new event\n"
                "`/joinbestball` - Join an event\n"
                "`/selectyourteam` - Build your roster\n"
                "`/addplayer` - Add player to roster\n"
                "`/reviewbestballroster` - View roster\n"
                "`/bestballstatus` - Check standings\n"
                "`/closebestball` - Lock rosters (admin)\n"
                "`/endbestball` - End event & generate payments"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)


class RosterBuildView(discord.ui.View):
    """View for interactive roster building."""
    
    def __init__(self, cog: BestBallCog, user_id: int, event_id: str, current_count: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.event_id = event_id
        self.current_count = current_count
    
    @discord.ui.button(label="QB", style=discord.ButtonStyle.primary)
    async def add_qb(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._prompt_player_search(interaction, "QB")
    
    @discord.ui.button(label="RB", style=discord.ButtonStyle.primary)
    async def add_rb(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._prompt_player_search(interaction, "RB")
    
    @discord.ui.button(label="WR", style=discord.ButtonStyle.primary)
    async def add_wr(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._prompt_player_search(interaction, "WR")
    
    @discord.ui.button(label="TE", style=discord.ButtonStyle.primary)
    async def add_te(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._prompt_player_search(interaction, "TE")
    
    @discord.ui.button(label="DST", style=discord.ButtonStyle.secondary)
    async def add_dst(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._prompt_player_search(interaction, "DST")
    
    async def _prompt_player_search(self, interaction: discord.Interaction, position: str):
        """Prompt user to search for a player."""
        modal = PlayerSearchModal(self.cog, self.event_id, self.user_id, position)
        await interaction.response.send_modal(modal)


class PlayerSearchModal(discord.ui.Modal):
    """Modal for searching and adding players."""
    
    def __init__(self, cog: BestBallCog, event_id: str, user_id: int, position: str):
        super().__init__(title=f"Add {position} to Roster")
        self.cog = cog
        self.event_id = event_id
        self.user_id = user_id
        self.position = position
        
        self.player_name = discord.ui.TextInput(
            label=f"Enter {position} name",
            placeholder="e.g., Mahomes, McCaffrey, Jefferson",
            required=True,
            max_length=50
        )
        self.add_item(self.player_name)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle player search submission."""
        await interaction.response.defer(ephemeral=True)
        
        # Search for player
        players = await self.cog._get_player_pool()
        matches = self.cog._search_players(
            self.player_name.value, players, self.position
        )
        
        if not matches:
            await interaction.followup.send(
                f"❌ No {self.position}s found matching '{self.player_name.value}'.",
                ephemeral=True
            )
            return
        
        if len(matches) == 1:
            # Auto-add single match
            player = matches[0]
            success = await self.cog._add_player_to_roster(
                self.event_id, self.user_id, player
            )
            
            if success:
                await interaction.followup.send(
                    f"✅ Added **{player['name']}** ({player['position']} - {player['team']}) to your roster!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Failed to add player. They may already be on your roster.",
                    ephemeral=True
                )
        else:
            # Show selection
            view = PlayerSelectView(self.cog, self.event_id, self.user_id, matches)
            
            embed = discord.Embed(
                title=f"🔍 Select {self.position}",
                description=f"Multiple matches for '{self.player_name.value}':",
                color=discord.Color.blue()
            )
            
            for i, p in enumerate(matches, 1):
                embed.add_field(
                    name=f"{i}. {p['name']}",
                    value=f"{p['position']} - {p['team']} ({p['overall']} OVR)",
                    inline=True
                )
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class PlayerSelectView(discord.ui.View):
    """View for selecting from multiple player matches."""
    
    def __init__(self, cog: BestBallCog, event_id: str, user_id: int, players: List[Dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.event_id = event_id
        self.user_id = user_id
        self.players = players
        
        # Add select menu
        options = [
            discord.SelectOption(
                label=f"{p['name']} ({p['team']})",
                description=f"{p['position']} - {p['overall']} OVR",
                value=str(i)
            )
            for i, p in enumerate(players)
        ]
        
        select = discord.ui.Select(
            placeholder="Select a player...",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        """Handle player selection."""
        index = int(interaction.data['values'][0])
        player = self.players[index]
        
        success = await self.cog._add_player_to_roster(
            self.event_id, self.user_id, player
        )
        
        if success:
            await interaction.response.send_message(
                f"✅ Added **{player['name']}** ({player['position']} - {player['team']}) to your roster!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Failed to add player. They may already be on your roster.",
                ephemeral=True
            )
        
        self.stop()


async def setup(bot):
    await bot.add_cog(BestBallCog(bot))
