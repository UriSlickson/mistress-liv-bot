"""
Registration Cog - Team owner self-registration system
Allows team owners to register themselves for announcements and helmet syncing.
"""

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import logging
import re

logger = logging.getLogger('MistressLIV.Registration')

# NFL Team abbreviations
NFL_TEAM_ABBREVS = [
    'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE',
    'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
    'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
    'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS'
]

# Team emoji mapping
NFL_TEAM_EMOJIS = {
    'ARI': '<:arihelmet:1458225285563539576>',
    'ATL': '<:atlhelmet:1458225284854681600>',
    'BAL': '<:balhelmet:1458225293029413029>',
    'BUF': '<:bufhelmet:1458225301019427121>',
    'CAR': '<:carhelmet:1458225316538343424>',
    'CHI': '<:chihelmet:1458225317255438397>',
    'CIN': '<:cinhelmet:1458225325136679187>',
    'CLE': '<:clehelmet:1458225333521223750>',
    'DAL': '<:dalhelmet:1458225340882194442>',
    'DEN': '<:denhelmet:1458225348402667570>',
    'DET': '<:dethelmet:1458225356434595861>',
    'GB': '<:gbhelmet:1458225364227629127>',
    'HOU': '<:houhelmet:1458225372708737164>',
    'IND': '<:indhelmet:1458225379473887405>',
    'JAX': '<:jaxhelmet:1458225387799843010>',
    'KC': '<:kchelmet:1458225396620406845>',
    'LAC': '<:lachelmet:1458225404061114389>',
    'LAR': '<:larhelmet:1458225412722442341>',
    'LV': '<:lvhelmet:1458225421043843082>',
    'MIA': '<:miahelmet:1458225429684162712>',
    'MIN': '<:minhelmet:1458225437670199326>',
    'NE': '<:nehelmet:1458225445249093805>',
    'NO': '<:nohelmet:1458225453247643699>',
    'NYG': '<:nyghelmet:1458225460625367080>',
    'NYJ': '<:nyjhelmet:1458225468917547170>',
    'PHI': '<:phihelmet:1458225480858730557>',
    'PIT': '<:pithelmet:1458225488915988573>',
    'SEA': '<:seahelmet:1458225497279533168>',
    'SF': '<:sfhelmet:1458225505307447306>',
    'TB': '<:tbhelmet:1458225513519902750>',
    'TEN': '<:tenhelmet:1458225521576906794>',
    'WAS': '<:washelmet:1458225529168576522>'
}

# Helmet emoji pattern for removal
HELMET_EMOJI_PATTERN = re.compile(r'<:\w+helmet:\d+>\s*')


class RegistrationCog(commands.Cog):
    """Cog for team owner registration."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'data/mistress_liv.db'
    
    def get_user_team_role(self, member: discord.Member) -> str:
        """Get the team abbreviation from user's roles."""
        for role in member.roles:
            if role.name.upper() in NFL_TEAM_ABBREVS:
                return role.name.upper()
        return None
    
    def register_team_owner(self, team_id: str, discord_id: int) -> bool:
        """Register a team owner's Discord ID in the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE teams SET user_discord_id = ? WHERE team_id = ?",
                (discord_id, team_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error registering team owner: {e}")
            return False
    
    def get_all_registered_owners(self) -> list:
        """Get all registered team owner Discord IDs."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT team_id, team_name, user_discord_id FROM teams WHERE user_discord_id IS NOT NULL"
            )
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            logger.error(f"Error getting registered owners: {e}")
            return []
    
    def remove_helmet_from_name(self, name: str) -> str:
        """Remove any helmet emoji prefix from a name."""
        name = HELMET_EMOJI_PATTERN.sub('', name)
        return name.strip()
    
    @app_commands.command(name="register", description="Register yourself as a team owner for announcements and helmet sync")
    async def register(self, interaction: discord.Interaction):
        """Register the user as a team owner based on their team role."""
        try:
            member = interaction.user
            team_abbrev = self.get_user_team_role(member)
            
            if not team_abbrev:
                await interaction.response.send_message(
                    "❌ You don't have a team role! Please contact an admin to get your team role first.",
                    ephemeral=True
                )
                return
            
            # Register in database
            if self.register_team_owner(team_abbrev, member.id):
                emoji = NFL_TEAM_EMOJIS.get(team_abbrev, '🏈')
                await interaction.response.send_message(
                    f"✅ **Registration successful!**\n\n"
                    f"{emoji} You are now registered as the **{team_abbrev}** team owner.\n\n"
                    f"You will now receive:\n"
                    f"• 📢 League announcements via DM\n"
                    f"• 🏈 Automatic helmet emoji sync\n"
                    f"• 📬 League-wide messages",
                    ephemeral=True
                )
                logger.info(f"Registered {member.display_name} ({member.id}) as {team_abbrev} owner")
            else:
                await interaction.response.send_message(
                    "❌ Failed to register. Please try again or contact an admin.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in register command: {e}")
            try:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            except:
                pass
    
    @app_commands.command(name="unregister", description="Unregister yourself from team owner announcements")
    async def unregister(self, interaction: discord.Interaction):
        """Unregister the user from team owner list."""
        try:
            member = interaction.user
            team_abbrev = self.get_user_team_role(member)
            
            if not team_abbrev:
                await interaction.response.send_message(
                    "❌ You don't have a team role!",
                    ephemeral=True
                )
                return
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE teams SET user_discord_id = NULL WHERE team_id = ? AND user_discord_id = ?",
                (team_abbrev, member.id)
            )
            conn.commit()
            conn.close()
            
            await interaction.response.send_message(
                f"✅ You have been unregistered from {team_abbrev} team owner notifications.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in unregister command: {e}")
            try:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            except:
                pass
    
    @app_commands.command(name="whoregistered", description="[Admin] See all registered team owners")
    @app_commands.default_permissions(administrator=True)
    async def who_registered(self, interaction: discord.Interaction):
        """Show all registered team owners."""
        try:
            owners = self.get_all_registered_owners()
            
            if not owners:
                await interaction.response.send_message(
                    "📋 **No team owners have registered yet.**\n\n"
                    "**Options to register team owners:**\n"
                    "• `/registeruser user:@someone team:SF` - Register a user manually\n"
                    "• `/registerall` - Post a message asking owners to register\n"
                    "• Have team owners run `/register` themselves",
                    ephemeral=True
                )
                return
            
            lines = ["📋 **Registered Team Owners:**\n"]
            for team_id, team_name, discord_id in owners:
                emoji = NFL_TEAM_EMOJIS.get(team_id, '🏈')
                lines.append(f"{emoji} **{team_id}** ({team_name}): <@{discord_id}>")
            
            lines.append(f"\n**Total:** {len(owners)}/32 teams registered")
            
            await interaction.response.send_message("\n".join(lines), ephemeral=True)
        except Exception as e:
            logger.error(f"Error in whoregistered command: {e}")
            try:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            except:
                pass
    
    @app_commands.command(name="registerall", description="[Admin] Prompt all team owners to register")
    @app_commands.default_permissions(administrator=True)
    async def register_all_prompt(self, interaction: discord.Interaction):
        """Post a message prompting all team owners to register."""
        try:
            embed = discord.Embed(
                title="📝 Team Owner Registration Required",
                description=(
                    "**All team owners please register!**\n\n"
                    "Run the `/register` command to register yourself as a team owner.\n\n"
                    "**Benefits of registering:**\n"
                    "• 📢 Receive league announcements via DM\n"
                    "• 🏈 Get your team helmet emoji added to your name\n"
                    "• 📬 Receive important league messages directly\n\n"
                    "**How to register:**\n"
                    "Simply type `/register` and press Enter!"
                ),
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in registerall command: {e}")
            try:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            except:
                pass
    
    @app_commands.command(name="registeruser", description="[Admin] Register a user as team owner (auto-detects team from their role)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        user="The user to register (mention them)",
        team="Optional: team abbreviation (auto-detects from role if not provided)"
    )
    async def register_user(self, interaction: discord.Interaction, user: discord.Member, team: str = None):
        """Manually register a user as a team owner. Auto-detects team from their role if not specified."""
        try:
            # Auto-detect team from user's role if not provided
            if team:
                team_upper = team.upper()
            else:
                team_upper = self.get_user_team_role(user)
                if not team_upper:
                    await interaction.response.send_message(
                        f"❌ {user.mention} doesn't have a team role and no team was specified.\n"
                        f"Either give them a team role first, or specify the team: `/registeruser user:@them team:SF`",
                        ephemeral=True
                    )
                    return
            
            if team_upper not in NFL_TEAM_ABBREVS:
                await interaction.response.send_message(
                    f"❌ Invalid team abbreviation: {team}\n"
                    f"Valid teams: {', '.join(sorted(NFL_TEAM_ABBREVS))}",
                    ephemeral=True
                )
                return
            
            if self.register_team_owner(team_upper, user.id):
                emoji = NFL_TEAM_EMOJIS.get(team_upper, '🏈')
                
                # Also try to sync their helmet
                helmet_result = ""
                try:
                    base_name = self.remove_helmet_from_name(user.display_name)
                    new_nickname = f"{emoji} {base_name}"
                    if len(new_nickname) > 32:
                        new_nickname = new_nickname[:32]
                    await user.edit(nick=new_nickname)
                    helmet_result = "\n🏈 Helmet emoji synced!"
                except discord.Forbidden:
                    helmet_result = "\n⚠️ Could not sync helmet (bot role needs to be higher)"
                except Exception as e:
                    helmet_result = f"\n⚠️ Could not sync helmet: {str(e)[:30]}"
                
                await interaction.response.send_message(
                    f"✅ Registered {user.mention} as the **{team_upper}** {emoji} team owner!{helmet_result}",
                    ephemeral=True
                )
                logger.info(f"Admin registered {user.display_name} ({user.id}) as {team_upper} owner")
            else:
                await interaction.response.send_message(
                    "❌ Failed to register user.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in registeruser command: {e}")
            try:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            except:
                pass
    
    @app_commands.command(name="bulkregister", description="[Admin] Register multiple mentioned users (auto-detects teams from roles)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        users="Mention all users to register: @user1 @user2 @user3 (teams auto-detected from their roles)"
    )
    async def bulk_register(self, interaction: discord.Interaction, users: str):
        """Register multiple users at once. Auto-detects teams from their roles."""
        try:
            await interaction.response.send_message("📝 Processing bulk registration...", ephemeral=True)
            
            guild = interaction.guild
            results = []
            success = 0
            failed = 0
            no_team_role = 0
            
            # Find all user mentions in the input
            user_ids = re.findall(r'<@!?(\d+)>', users)
            
            if not user_ids:
                await interaction.edit_original_response(
                    content="❌ No users mentioned! Usage: `/bulkregister users:@user1 @user2 @user3`"
                )
                return
            
            for user_id_str in user_ids:
                user_id = int(user_id_str)
                
                # Get the member
                try:
                    member = await guild.fetch_member(user_id)
                except:
                    results.append(f"❌ <@{user_id}> - User not found")
                    failed += 1
                    continue
                
                # Auto-detect team from their role
                team = self.get_user_team_role(member)
                if not team:
                    results.append(f"⚠️ <@{user_id}> - No team role found")
                    no_team_role += 1
                    continue
                
                # Register the user
                if self.register_team_owner(team, user_id):
                    emoji = NFL_TEAM_EMOJIS.get(team, '🏈')
                    results.append(f"✅ {emoji} <@{user_id}> → {team}")
                    success += 1
                else:
                    results.append(f"❌ <@{user_id}> - Failed to register as {team}")
                    failed += 1
            
            # Build response
            response = ["📝 **Bulk Registration Complete**\n"]
            response.append(f"✅ Registered: {success}")
            if failed > 0:
                response.append(f"❌ Failed: {failed}")
            if no_team_role > 0:
                response.append(f"⚠️ No team role: {no_team_role}")
            response.append("")
            response.extend(results[:20])  # Limit to 20 results
            
            if len(results) > 20:
                response.append(f"\n... and {len(results) - 20} more")
            
            await interaction.edit_original_response(content="\n".join(response))
        except Exception as e:
            logger.error(f"Error in bulkregister command: {e}")
            try:
                await interaction.edit_original_response(content=f"❌ Error: {e}")
            except:
                pass


async def setup(bot):
    await bot.add_cog(RegistrationCog(bot))
