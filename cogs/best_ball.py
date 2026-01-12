"""
Best Ball Fantasy Football Cog
Features:
- Create and manage Best Ball events
- Roster building with autocomplete player search
- Automatic weekly lineup optimization
- PPR scoring based on Madden sim stats (via Snallabot)
- Loser-pays-winner payout system (bottom pays top)
- Integration with wager/payment tracking

CONSOLIDATED COMMANDS:
/bestball start - Create a new event
/bestball join - Join an event
/bestball roster - View/manage roster
/bestball add - Add a player
/bestball remove - Remove a player
/bestball status - Check standings
/bestball rules - View rules
/bestball close - Close event (admin)
/bestball end - End event (admin)
/bestball cancel - Cancel event (admin)
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

# Snallabot API base URL
SNALLABOT_API_BASE = "https://snallabot.me"

# Madden team ID to abbreviation mapping
TEAM_ID_TO_ABBR = {
    0: 'CHI', 1: 'CIN', 2: 'BUF', 3: 'DEN', 4: 'CLE', 5: 'TB', 6: 'ARI', 7: 'LAC',
    8: 'KC', 9: 'IND', 10: 'DAL', 11: 'MIA', 12: 'PHI', 13: 'ATL', 14: 'SF', 15: 'NYG',
    16: 'JAX', 17: 'NYJ', 18: 'DET', 19: 'GB', 20: 'CAR', 21: 'NE', 22: 'LV', 23: 'LAR',
    24: 'BAL', 25: 'WAS', 26: 'NO', 27: 'SEA', 28: 'PIT', 29: 'TEN', 30: 'MIN', 31: 'HOU'
}

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
    'fumble_lost': -2,
    'bonus_100_rush_yards': 3,
    'bonus_100_rec_yards': 3,
    'bonus_300_pass_yards': 3,
    'dst_sack': 1,
    'dst_interception': 2,
    'dst_fumble_recovery': 2,
    'dst_td': 6,
    'dst_safety': 2,
    'dst_points_allowed_0': 10,
    'dst_points_allowed_1_6': 7,
    'dst_points_allowed_7_13': 4,
    'dst_points_allowed_14_20': 1,
    'dst_points_allowed_21_27': 0,
    'dst_points_allowed_28_34': -1,
    'dst_points_allowed_35_plus': -4,
}

# Roster requirements
ROSTER_SIZE = 20
MIN_ROSTER = {'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'DST': 0}
MAX_ROSTER = {'QB': 2, 'RB': 6, 'WR': 7, 'TE': 3, 'DST': 2}
STARTING_LINEUP = {'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 2, 'DST': 1}


class BestBallCog(commands.Cog):
    """Cog for Best Ball fantasy football management."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "data/mistress_liv.db"
        self.player_cache = {}
        self.cache_timestamp = None
        self._init_tables()
        
    def _init_tables(self):
        """Initialize Best Ball database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS best_ball_events (
                event_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                event_name TEXT NOT NULL,
                entry_fee REAL DEFAULT 50.0,
                status TEXT DEFAULT 'open',
                start_week INTEGER DEFAULT 1,
                duration_weeks INTEGER DEFAULT 17,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                ended_at TIMESTAMP
            )
        ''')
        
        # Participants table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS best_ball_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_points REAL DEFAULT 0.0,
                FOREIGN KEY (event_id) REFERENCES best_ball_events(event_id),
                UNIQUE(event_id, user_id)
            )
        ''')
        
        # Rosters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS best_ball_rosters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                position TEXT NOT NULL,
                team TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES best_ball_events(event_id),
                UNIQUE(event_id, user_id, player_id)
            )
        ''')
        
        # Weekly scores table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS best_ball_weekly_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                points REAL DEFAULT 0.0,
                lineup_json TEXT,
                FOREIGN KEY (event_id) REFERENCES best_ball_events(event_id),
                UNIQUE(event_id, user_id, week)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Best Ball tables initialized")
    
    def _get_league_config(self, guild_id: int) -> dict:
        """Get league configuration for a guild."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT league_id, platform FROM guild_leagues 
            WHERE guild_id = ? AND is_active = 1
        ''', (guild_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {'league_id': row[0], 'platform': row[1]}
        return {'league_id': 'liv', 'platform': 'xboxone'}
    
    async def _fetch_players(self, guild_id: int) -> List[Dict]:
        """Fetch players from Snallabot API."""
        config = self._get_league_config(guild_id)
        league_id = config.get('league_id', 'liv')
        platform = config.get('platform', 'xboxone')
        
        url = f"{SNALLABOT_API_BASE}/{platform}/{league_id}/freeagents"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('rosterInfoList', [])
        except Exception as e:
            logger.error(f"Error fetching players: {e}")
        return []
    
    async def _refresh_player_cache(self, guild_id: int):
        """Refresh the player cache from Snallabot."""
        players = await self._fetch_players(guild_id)
        if players:
            self.player_cache[guild_id] = players
            self.cache_timestamp = datetime.now()
            logger.info(f"Refreshed player cache for guild {guild_id}: {len(players)} players")
    
    def _check_welcher(self, user_id: int) -> bool:
        """Check if user is banned as a welcher."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM welchers WHERE user_id = ? AND is_active = 1', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def _get_roster_status(self, event_id: str, user_id: int) -> Dict:
        """Get roster status showing positions filled and needed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT position, COUNT(*) FROM best_ball_rosters
            WHERE event_id = ? AND user_id = ?
            GROUP BY position
        ''', (event_id, user_id))
        
        counts = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        
        total = sum(counts.values())
        status = {
            'total': total,
            'remaining': ROSTER_SIZE - total,
            'positions': {}
        }
        
        for pos in ['QB', 'RB', 'WR', 'TE', 'DST']:
            current = counts.get(pos, 0)
            min_req = MIN_ROSTER.get(pos, 0)
            max_req = MAX_ROSTER.get(pos, 0)
            needed = max(0, min_req - current)
            can_add = max_req - current
            status['positions'][pos] = {
                'current': current,
                'min': min_req,
                'max': max_req,
                'needed': needed,
                'can_add': can_add
            }
        
        return status
    
    async def _player_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for player names."""
        guild_id = interaction.guild_id
        
        if guild_id not in self.player_cache:
            await self._refresh_player_cache(guild_id)
        
        players = self.player_cache.get(guild_id, [])
        matches = []
        
        current_lower = current.lower()
        for player in players:
            name = f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()
            if current_lower in name.lower():
                pos = player.get('position', 'UNK')
                team_id = player.get('teamId', -1)
                team = TEAM_ID_TO_ABBR.get(team_id, 'FA')
                display = f"{name} ({pos} - {team})"
                matches.append(app_commands.Choice(name=display[:100], value=name))
                if len(matches) >= 25:
                    break
        
        return matches
    
    async def _event_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for event selection by creator name."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT event_id, event_name, creator_id FROM best_ball_events
            WHERE guild_id = ? AND status IN ('open', 'active')
        ''', (interaction.guild_id,))
        events = cursor.fetchall()
        conn.close()
        
        choices = []
        for event_id, event_name, creator_id in events:
            member = interaction.guild.get_member(creator_id)
            creator_name = member.display_name if member else f"User {creator_id}"
            display = f"{event_name} (by {creator_name})"
            if current.lower() in display.lower():
                choices.append(app_commands.Choice(name=display[:100], value=event_id))
                if len(choices) >= 25:
                    break
        
        return choices

    # ==================== COMMAND GROUP ====================
    
    bestball_group = app_commands.Group(name="bestball", description="Best Ball fantasy football commands")
    
    @bestball_group.command(name="start", description="Create a new Best Ball event")
    @app_commands.describe(
        event_name="Name for the event",
        entry_fee="Entry fee amount (default: $50)",
        duration_weeks="Number of weeks (default: 17)",
        start_week="Starting week number (default: 1)"
    )
    async def bestball_start(
        self,
        interaction: discord.Interaction,
        event_name: str,
        entry_fee: float = 50.0,
        duration_weeks: int = 17,
        start_week: int = 1
    ):
        """Create a new Best Ball event."""
        await interaction.response.defer()
        
        event_id = f"BB-{interaction.guild_id}-{int(datetime.now().timestamp())}"
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO best_ball_events (event_id, guild_id, creator_id, event_name, entry_fee, duration_weeks, start_week)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (event_id, interaction.guild_id, interaction.user.id, event_name, entry_fee, duration_weeks, start_week))
            conn.commit()
            
            embed = discord.Embed(
                title="🏈 Best Ball Event Created!",
                description=f"**{event_name}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Entry Fee", value=f"${entry_fee:.2f}", inline=True)
            embed.add_field(name="Duration", value=f"{duration_weeks} weeks", inline=True)
            embed.add_field(name="Start Week", value=str(start_week), inline=True)
            embed.add_field(name="Join Command", value=f"`/bestball join`", inline=False)
            embed.set_footer(text=f"Created by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error creating Best Ball event: {e}")
            await interaction.followup.send("❌ Error creating event. Please try again.", ephemeral=True)
        finally:
            conn.close()
    
    @bestball_group.command(name="join", description="Join a Best Ball event")
    @app_commands.describe(event="Select the event to join")
    @app_commands.autocomplete(event=_event_autocomplete)
    async def bestball_join(self, interaction: discord.Interaction, event: str):
        """Join a Best Ball event."""
        await interaction.response.defer()
        
        # Check welcher status
        if self._check_welcher(interaction.user.id):
            await interaction.followup.send(
                "🚫 You are currently banned from Best Ball events due to unpaid debts. "
                "Please settle your outstanding payments to participate.",
                ephemeral=True
            )
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if event exists and is open
        cursor.execute('SELECT status, event_name, entry_fee FROM best_ball_events WHERE event_id = ?', (event,))
        row = cursor.fetchone()
        
        if not row:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            conn.close()
            return
        
        status, event_name, entry_fee = row
        
        if status != 'open':
            await interaction.followup.send("❌ This event is no longer accepting participants.", ephemeral=True)
            conn.close()
            return
        
        # Check if already joined
        cursor.execute('SELECT 1 FROM best_ball_participants WHERE event_id = ? AND user_id = ?', (event, interaction.user.id))
        if cursor.fetchone():
            await interaction.followup.send("❌ You've already joined this event!", ephemeral=True)
            conn.close()
            return
        
        try:
            cursor.execute('''
                INSERT INTO best_ball_participants (event_id, user_id)
                VALUES (?, ?)
            ''', (event, interaction.user.id))
            conn.commit()
            
            embed = discord.Embed(
                title="✅ Joined Best Ball Event!",
                description=f"You've joined **{event_name}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Entry Fee", value=f"${entry_fee:.2f}", inline=True)
            embed.add_field(name="Next Step", value="Use `/bestball roster` to start building your team!", inline=False)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error joining Best Ball event: {e}")
            await interaction.followup.send("❌ Error joining event. Please try again.", ephemeral=True)
        finally:
            conn.close()
    
    @bestball_group.command(name="roster", description="View your roster and what positions you need")
    @app_commands.describe(event="Select the event")
    @app_commands.autocomplete(event=_event_autocomplete)
    async def bestball_roster(self, interaction: discord.Interaction, event: str):
        """View roster status and positions needed."""
        await interaction.response.defer()
        
        status = self._get_roster_status(event, interaction.user.id)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT event_name FROM best_ball_events WHERE event_id = ?', (event,))
        row = cursor.fetchone()
        event_name = row[0] if row else "Unknown Event"
        
        cursor.execute('''
            SELECT player_name, position, team FROM best_ball_rosters
            WHERE event_id = ? AND user_id = ?
            ORDER BY position, player_name
        ''', (event, interaction.user.id))
        players = cursor.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title=f"🏈 Your Roster - {event_name}",
            description=f"**{status['total']}/{ROSTER_SIZE}** players | **{status['remaining']}** slots remaining",
            color=discord.Color.blue()
        )
        
        # Position breakdown
        pos_text = ""
        for pos in ['QB', 'RB', 'WR', 'TE', 'DST']:
            p = status['positions'][pos]
            status_emoji = "✅" if p['current'] >= p['min'] else "⚠️"
            pos_text += f"{status_emoji} **{pos}:** {p['current']}/{p['min']}-{p['max']}"
            if p['needed'] > 0:
                pos_text += f" (need {p['needed']} more)"
            pos_text += "\n"
        
        embed.add_field(name="📊 Position Status", value=pos_text, inline=False)
        
        # Current roster by position
        if players:
            roster_by_pos = {}
            for name, pos, team in players:
                if pos not in roster_by_pos:
                    roster_by_pos[pos] = []
                roster_by_pos[pos].append(f"{name} ({team})")
            
            for pos in ['QB', 'RB', 'WR', 'TE', 'DST']:
                if pos in roster_by_pos:
                    embed.add_field(
                        name=f"{pos}s",
                        value="\n".join(roster_by_pos[pos]),
                        inline=True
                    )
        else:
            embed.add_field(name="📋 Roster", value="No players added yet. Use `/bestball add` to start!", inline=False)
        
        embed.set_footer(text="Use /bestball add <player> to add players")
        await interaction.followup.send(embed=embed)
    
    @bestball_group.command(name="add", description="Add a player to your roster")
    @app_commands.describe(event="Select the event", player="Search for a player")
    @app_commands.autocomplete(event=_event_autocomplete, player=_player_autocomplete)
    async def bestball_add(self, interaction: discord.Interaction, event: str, player: str):
        """Add a player to roster."""
        await interaction.response.defer()
        
        guild_id = interaction.guild_id
        
        # Find player in cache
        if guild_id not in self.player_cache:
            await self._refresh_player_cache(guild_id)
        
        players = self.player_cache.get(guild_id, [])
        player_data = None
        
        for p in players:
            name = f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
            if name.lower() == player.lower():
                player_data = p
                break
        
        if not player_data:
            await interaction.followup.send(f"❌ Player '{player}' not found. Try the autocomplete suggestions.", ephemeral=True)
            return
        
        player_name = f"{player_data.get('firstName', '')} {player_data.get('lastName', '')}".strip()
        position = player_data.get('position', 'UNK')
        team_id = player_data.get('teamId', -1)
        team = TEAM_ID_TO_ABBR.get(team_id, 'FA')
        player_id = str(player_data.get('rosterId', player_name))
        
        # Check roster limits
        status = self._get_roster_status(event, interaction.user.id)
        
        if status['total'] >= ROSTER_SIZE:
            await interaction.followup.send("❌ Your roster is full (20 players).", ephemeral=True)
            return
        
        pos_status = status['positions'].get(position, {})
        if pos_status.get('can_add', 0) <= 0:
            await interaction.followup.send(f"❌ You've reached the maximum {position}s allowed.", ephemeral=True)
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO best_ball_rosters (event_id, user_id, player_id, player_name, position, team)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (event, interaction.user.id, player_id, player_name, position, team))
            conn.commit()
            
            new_status = self._get_roster_status(event, interaction.user.id)
            
            embed = discord.Embed(
                title="✅ Player Added!",
                description=f"**{player_name}** ({position} - {team})",
                color=discord.Color.green()
            )
            embed.add_field(name="Roster", value=f"{new_status['total']}/{ROSTER_SIZE}", inline=True)
            embed.add_field(name="Remaining", value=str(new_status['remaining']), inline=True)
            
            await interaction.followup.send(embed=embed)
            
        except sqlite3.IntegrityError:
            await interaction.followup.send("❌ This player is already on your roster.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error adding player: {e}")
            await interaction.followup.send("❌ Error adding player. Please try again.", ephemeral=True)
        finally:
            conn.close()
    
    @bestball_group.command(name="remove", description="Remove a player from your roster")
    @app_commands.describe(event="Select the event", player="Player name to remove")
    @app_commands.autocomplete(event=_event_autocomplete)
    async def bestball_remove(self, interaction: discord.Interaction, event: str, player: str):
        """Remove a player from roster."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if event is still open
        cursor.execute('SELECT status FROM best_ball_events WHERE event_id = ?', (event,))
        row = cursor.fetchone()
        if row and row[0] != 'open':
            await interaction.followup.send("❌ Cannot modify roster - event has started.", ephemeral=True)
            conn.close()
            return
        
        cursor.execute('''
            DELETE FROM best_ball_rosters
            WHERE event_id = ? AND user_id = ? AND player_name LIKE ?
        ''', (event, interaction.user.id, f"%{player}%"))
        
        if cursor.rowcount > 0:
            conn.commit()
            await interaction.followup.send(f"✅ Removed **{player}** from your roster.")
        else:
            await interaction.followup.send(f"❌ Player '{player}' not found on your roster.", ephemeral=True)
        
        conn.close()
    
    @bestball_group.command(name="status", description="Check event standings and leaderboard")
    @app_commands.describe(event="Select the event")
    @app_commands.autocomplete(event=_event_autocomplete)
    async def bestball_status(self, interaction: discord.Interaction, event: str):
        """View event status and standings."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT event_name, entry_fee, status, duration_weeks, start_week
            FROM best_ball_events WHERE event_id = ?
        ''', (event,))
        event_row = cursor.fetchone()
        
        if not event_row:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            conn.close()
            return
        
        event_name, entry_fee, status, duration, start_week = event_row
        
        cursor.execute('''
            SELECT user_id, total_points FROM best_ball_participants
            WHERE event_id = ?
            ORDER BY total_points DESC
        ''', (event,))
        participants = cursor.fetchall()
        conn.close()
        
        embed = discord.Embed(
            title=f"🏈 {event_name}",
            color=discord.Color.blue()
        )
        
        status_emoji = {"open": "🟢", "active": "🟡", "completed": "🔴"}.get(status, "⚪")
        embed.add_field(name="Status", value=f"{status_emoji} {status.title()}", inline=True)
        embed.add_field(name="Entry Fee", value=f"${entry_fee:.2f}", inline=True)
        embed.add_field(name="Participants", value=str(len(participants)), inline=True)
        
        if participants:
            standings = ""
            for i, (user_id, points) in enumerate(participants[:10], 1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"User {user_id}"
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                standings += f"{medal} {name}: {points:.1f} pts\n"
            
            embed.add_field(name="📊 Standings", value=standings or "No scores yet", inline=False)
        
        await interaction.followup.send(embed=embed)
    
    @bestball_group.command(name="rules", description="View Best Ball rules and scoring")
    async def bestball_rules(self, interaction: discord.Interaction):
        """Display Best Ball rules."""
        embed = discord.Embed(
            title="🏈 Best Ball Rules",
            description="Build a roster and let the bot optimize your lineup each week!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 Roster (20 players)",
            value=(
                f"• **QB:** {MIN_ROSTER['QB']}-{MAX_ROSTER['QB']}\n"
                f"• **RB:** {MIN_ROSTER['RB']}-{MAX_ROSTER['RB']}\n"
                f"• **WR:** {MIN_ROSTER['WR']}-{MAX_ROSTER['WR']}\n"
                f"• **TE:** {MIN_ROSTER['TE']}-{MAX_ROSTER['TE']}\n"
                f"• **DST:** {MIN_ROSTER['DST']}-{MAX_ROSTER['DST']}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🎯 Weekly Starters",
            value="1 QB, 2 RB, 3 WR, 1 TE\n2 FLEX (RB/WR/TE), 1 DST",
            inline=True
        )
        
        embed.add_field(
            name="📊 Scoring (PPR)",
            value=(
                "**Pass:** 0.04/yd, 4/TD, -2/INT\n"
                "**Rush/Rec:** 0.1/yd, 6/TD, 1/rec\n"
                "**Bonus:** +3 for 100+ rush/rec, 300+ pass"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💸 Payouts",
            value="**Losers pay Winners:**\nLast → 1st, 2nd-last → 2nd, etc.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @bestball_group.command(name="close", description="[Admin] Close event and start scoring")
    @app_commands.describe(event="Select the event to close")
    @app_commands.autocomplete(event=_event_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def bestball_close(self, interaction: discord.Interaction, event: str):
        """Close event for new participants and start scoring."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE best_ball_events SET status = 'active', closed_at = CURRENT_TIMESTAMP
            WHERE event_id = ? AND status = 'open'
        ''', (event,))
        
        if cursor.rowcount > 0:
            conn.commit()
            await interaction.followup.send("✅ Event closed! Rosters are now locked and scoring will begin.")
        else:
            await interaction.followup.send("❌ Event not found or already closed.", ephemeral=True)
        
        conn.close()
    
    @bestball_group.command(name="end", description="[Admin] End event and generate payments")
    @app_commands.describe(event="Select the event to end")
    @app_commands.autocomplete(event=_event_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def bestball_end(self, interaction: discord.Interaction, event: str):
        """End event and generate payment obligations."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT event_name, entry_fee FROM best_ball_events WHERE event_id = ?', (event,))
        event_row = cursor.fetchone()
        
        if not event_row:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            conn.close()
            return
        
        event_name, entry_fee = event_row
        
        # Get final standings
        cursor.execute('''
            SELECT user_id, total_points FROM best_ball_participants
            WHERE event_id = ?
            ORDER BY total_points DESC
        ''', (event,))
        standings = cursor.fetchall()
        
        if len(standings) < 2:
            await interaction.followup.send("❌ Need at least 2 participants to generate payments.", ephemeral=True)
            conn.close()
            return
        
        # Generate loser-pays-winner payments
        num_pairs = len(standings) // 2
        payments_created = []
        
        for i in range(num_pairs):
            winner_id = standings[i][0]
            loser_id = standings[-(i+1)][0]
            
            cursor.execute('''
                INSERT INTO payments (payer_discord_id, payee_discord_id, amount, reason, season, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            ''', (loser_id, winner_id, entry_fee, f"Best Ball: {event_name}", 2026))
            
            winner = interaction.guild.get_member(winner_id)
            loser = interaction.guild.get_member(loser_id)
            payments_created.append(f"• {loser.display_name if loser else loser_id} → {winner.display_name if winner else winner_id}: ${entry_fee:.2f}")
        
        # Mark event as completed
        cursor.execute('''
            UPDATE best_ball_events SET status = 'completed', ended_at = CURRENT_TIMESTAMP
            WHERE event_id = ?
        ''', (event,))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title=f"🏆 {event_name} - Final Results",
            description="Event completed! Payments generated.",
            color=discord.Color.gold()
        )
        
        # Final standings
        standings_text = ""
        for i, (user_id, points) in enumerate(standings[:10], 1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            standings_text += f"{medal} {name}: {points:.1f} pts\n"
        
        embed.add_field(name="📊 Final Standings", value=standings_text, inline=False)
        embed.add_field(name="💸 Payments", value="\n".join(payments_created) or "None", inline=False)
        
        await interaction.followup.send(embed=embed)
    
    @bestball_group.command(name="cancel", description="[Admin] Cancel a Best Ball event")
    @app_commands.describe(event="Select the event to cancel")
    @app_commands.autocomplete(event=_event_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def bestball_cancel(self, interaction: discord.Interaction, event: str):
        """Cancel an event and remove all data."""
        await interaction.response.defer()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT event_name FROM best_ball_events WHERE event_id = ?', (event,))
        row = cursor.fetchone()
        
        if not row:
            await interaction.followup.send("❌ Event not found.", ephemeral=True)
            conn.close()
            return
        
        event_name = row[0]
        
        # Delete all related data
        cursor.execute('DELETE FROM best_ball_weekly_scores WHERE event_id = ?', (event,))
        cursor.execute('DELETE FROM best_ball_rosters WHERE event_id = ?', (event,))
        cursor.execute('DELETE FROM best_ball_participants WHERE event_id = ?', (event,))
        cursor.execute('DELETE FROM best_ball_events WHERE event_id = ?', (event,))
        
        conn.commit()
        conn.close()
        
        await interaction.followup.send(f"✅ Best Ball event **{event_name}** has been cancelled and all data removed.")


async def setup(bot):
    await bot.add_cog(BestBallCog(bot))
