#!/usr/bin/env python3
"""Populate the correct database (data/mistress_liv.db) with Season 2025 test data."""

import sqlite3
from datetime import datetime

# Connect to the correct database
conn = sqlite3.connect('data/mistress_liv.db')
cursor = conn.cursor()

# Clear existing test data for season 2025
cursor.execute("DELETE FROM season_results WHERE season_year = 2025")
cursor.execute("DELETE FROM playoff_results WHERE season = 2025")
cursor.execute("DELETE FROM payments WHERE season_year = 2025")
cursor.execute("DELETE FROM season_standings WHERE season = 2025")

# NFC Standings from Season 2025 (MyMadden)
nfc_standings = [
    (1, 'PHI', 14, 3),   # Eagles - 1 seed
    (2, 'SEA', 13, 4),   # Seahawks - 2 seed
    (3, 'DET', 12, 5),   # Lions - 3 seed
    (4, 'LAR', 11, 6),   # Rams - 4 seed
    (5, 'GB', 10, 7),    # Packers - 5 seed
    (6, 'NO', 9, 8),     # Saints - 6 seed
    (7, 'NYG', 8, 9),    # Giants - 7 seed
    (8, 'TB', 7, 10),    # Buccaneers - 8 seed
    (9, 'ATL', 7, 10),   # Falcons - 9 seed
    (10, 'ARI', 6, 11),  # Cardinals - 10 seed
    (11, 'CHI', 5, 12),  # Bears - 11 seed
    (12, 'MIN', 4, 13),  # Vikings - 12 seed
    (13, 'SF', 4, 13),   # 49ers - 13 seed
    (14, 'CAR', 3, 14),  # Panthers - 14 seed
    (15, 'DAL', 3, 14),  # Cowboys - 15 seed
    (16, 'WAS', 2, 15),  # Commanders - 16 seed
]

# Insert NFC standings into season_standings
for seed, team, wins, losses in nfc_standings:
    cursor.execute('''
        INSERT INTO season_standings (season, conference, seed, team_id, user_discord_id, wins, losses)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (2025, 'NFC', seed, team, 1000 + seed, wins, losses))

# Insert into season_results for the query
for seed, team, wins, losses in nfc_standings:
    cursor.execute('''
        INSERT INTO season_results (season_year, user_discord_id, team_id, conference, final_seed, wins, losses)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (2025, 1000 + seed, team, 'NFC', seed, wins, losses))

# Playoff Results from Season 2025 (round, winner_team, winner_discord_id, loser_team, loser_discord_id)
playoff_games = [
    # Wildcard Round
    ('wildcard', 'DET', 1003, 'GB', 1005),      # Lions def. Packers
    ('wildcard', 'PHI', 1001, 'NYG', 1007),     # Eagles def. Giants
    ('wildcard', 'LAR', 1004, 'NO', 1006),      # Rams def. Saints
    # Divisional Round
    ('divisional', 'LAR', 1004, 'DET', 1003),   # Rams def. Lions
    ('divisional', 'PHI', 1001, 'SEA', 1002),   # Eagles def. Seahawks
    # Conference Championship
    ('conference', 'LAR', 1004, 'PHI', 1001),   # Rams def. Eagles
    # Super Bowl (Jets won - AFC team)
    ('superbowl', 'NYJ', 2001, 'LAR', 1004),    # Jets def. Rams
]

for round_name, winner_team, winner_id, loser_team, loser_id in playoff_games:
    cursor.execute('''
        INSERT INTO playoff_results (season, round, winner_discord_id, winner_team_id, loser_discord_id, loser_team_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (2025, round_name, winner_id, winner_team, loser_id, loser_team, datetime.now().isoformat()))

# Generate sample payments (NFC seeds 8-16 pay winners)
# Simplified payment structure for testing
sample_payments = [
    (1008, 1001, 100, 'NFC Seed 8 pays Super Bowl winner'),  # Seed 8 pays SB winner
    (1009, 1001, 100, 'NFC Seed 9 pays Super Bowl winner'),  # Seed 9 pays SB winner
    (1010, 1001, 100, 'NFC Seed 10 pays Super Bowl winner'), # Seed 10 pays SB winner
    (1011, 1004, 100, 'NFC Seed 11 pays Conference winner'), # Seed 11 pays Conf winner
    (1012, 1004, 100, 'NFC Seed 12 pays Conference winner'), # Seed 12 pays Conf winner
]

for payer_id, payee_id, amount, reason in sample_payments:
    cursor.execute('''
        INSERT INTO payments (season_year, payer_discord_id, payee_discord_id, amount, reason, is_paid, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (2025, payer_id, payee_id, amount, reason, 0, datetime.now().isoformat()))

conn.commit()
conn.close()

print("✅ Season 2025 test data populated in data/mistress_liv.db!")
print("   - NFC Standings: 16 teams")
print("   - Playoff Results: 7 games")
print("   - Payments: 5 sample payments")
