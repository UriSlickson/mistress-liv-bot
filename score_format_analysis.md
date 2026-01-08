# Score Format Analysis for Auto-Settlement Feature

## MyMadden Website Format

From the MyMadden website (https://mymadden.com/lg/liv/schedule), game results are displayed as:

### Visual Format:
```
[Away Team Logo]    [Home Team Logo]
   Eagles              Giants
     28                  25
   12-5-0              13-4-0
  FW: None         Started 1 Time
```

### Key Data Points:
- **Away Team**: Eagles (left side)
- **Home Team**: Giants (right side)  
- **Away Score**: 28
- **Home Score**: 25
- **Away Record**: 12-5-0
- **Home Record**: 13-4-0
- **Winner**: Eagles (higher score wins)

## Discord #scores Channel Format (MyMadden Bot)

From the #scores channel in Discord, the MyMadden bot posts:
```
LIV on MyMadden
Ravens 11-6-0 35 AT 17 Steelers 11-6-0
@Repenters AT @hi
2027 | Post Season | Divisional
```

### Parsed Format:
- **Away Team**: Ravens
- **Away Record**: 11-6-0
- **Away Score**: 35
- **"AT"**: Separator indicating "at" (away @ home)
- **Home Score**: 17
- **Home Team**: Steelers
- **Home Record**: 11-6-0
- **Away Owner**: @Repenters
- **Home Owner**: @hi
- **Season Info**: 2027 | Post Season | Divisional

### Regex Pattern for Discord Messages:
```
^LIV on MyMadden\n(.+?) (\d+-\d+-\d+) (\d+) AT (\d+) (.+?) (\d+-\d+-\d+)\n@(.+?) AT @(.+?)\n(\d+) \| (.+?) \| (.+)$
```

## Winner Determination Logic:
1. Parse away_score and home_score from the message
2. If away_score > home_score: away_team wins
3. If home_score > away_score: home_team wins
4. Ties are rare but possible (would need special handling)

## Implementation Strategy for Auto-Settlement:

### Option 1: Monitor Discord #scores Channel
- Listen for messages from MyMadden bot in #scores channel
- Parse the message using regex
- Extract: away_team, home_team, away_score, home_score, week, season_type
- Determine winner based on scores
- Find matching wagers and settle them automatically

### Option 2: Scrape MyMadden Website
- Periodically check https://mymadden.com/lg/liv/schedule
- Parse game results from the schedule page
- Match games to pending wagers
- Settle wagers automatically

### Recommended: Option 1 (Discord Channel Monitoring)
- Real-time detection when scores are posted
- No external web scraping needed
- Leverages existing MyMadden bot integration
- More reliable and immediate

## Team Name Mapping (for matching wagers to games):
Need to handle variations:
- "Ravens" vs "Baltimore Ravens" vs "BAL"
- "Steelers" vs "Pittsburgh Steelers" vs "PIT"

Standard NFL team abbreviations should be supported.


## More Game Examples from MyMadden (2027 Regular Season Week 1):

| Away Team | Away Score | Home Team | Home Score | Winner |
|-----------|------------|-----------|------------|--------|
| Eagles | 28 | Giants | 25 | Eagles |
| Saints | 24 | Buccaneers | 3 | Saints |
| Bills | 10 | Colts | 40 | Colts |
| Steelers | 29 | Ravens | 21 | Steelers |
| Jets | 26 | Patriots | 23 | Jets |

### Pattern Confirmed:
- Left side = Away team
- Right side = Home team
- Higher score = Winner
- Records shown below scores (e.g., 11-6-0)
- "FW: None" or "Started 1 Time" indicates game status

### Key Insight:
The MyMadden bot in Discord posts the SAME data but in text format:
`[Away Team] [Record] [Away Score] AT [Home Score] [Home Team] [Record]`

This is consistent and parseable!
