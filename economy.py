import discord
from discord.ext import commands, tasks
import aiosqlite
import asyncio
import random
import time
from utils.db import Database  # Import the Database class from utils.db
from discord.ui import View, Button, Modal, TextInput

class BotSelectionModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Select Bot Battle Mode")
        self.bot_mode = None
        self.add_item(discord.ui.TextInput(
            label="Bot Battle Mode",
            placeholder="Enter 1v1, 2v2, 3v3, or 4v4",
            required=True,
            max_length=3
        ))

    async def on_submit(self, interaction: discord.Interaction):
        self.bot_mode = self.children[0].value
        if self.bot_mode not in ['1v1', '2v2', '3v3', '4v4']:
            await interaction.response.send_message("Invalid mode. Please choose 1v1, 2v2, 3v3, or 4v4.", ephemeral=True)
        else:
            await interaction.response.defer()

class CaseBattleView(discord.ui.View):
    def __init__(self, ctx, host, cog, case_data):  
        super().__init__(timeout=300) 
        self.ctx = ctx  # Store the context
        self.host = host
        self.cog = cog
        self.players = [host]
        self.case_data = case_data

    @discord.ui.button(label="Select Cases", style=discord.ButtonStyle.primary)
    async def select_cases(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("Only the host can select cases!", ephemeral=True)
            return

        modal = CaseSelectionModal(self.case_data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        
        if modal.selected_cases:
            potential_total_bet = sum(
                self.case_data[case]['price'] * amount 
                for case, amount in modal.selected_cases.items()
            )
            
            # Check if host has enough balance before updating selected cases
            if not await self.cog.check_balance(self.host, potential_total_bet):
                await interaction.followup.send("You don't have enough balance to select these cases!", ephemeral=True)
            else:
                self.selected_cases.update(modal.selected_cases)
                self.total_bet = potential_total_bet
                await interaction.followup.send(f"Added cases to your selection. Total bet: ${self.total_bet:,}", ephemeral=True)
                await self.update_message(interaction)



        
        if modal.selected_cases:
            self.selected_cases.update(modal.selected_cases)
            self.total_bet = self.calculate_total_bet()
            
            # Check if host has enough balance
            if not await self.economy_cog.check_balance(self.host, self.total_bet):
                await interaction.followup.send("You don't have enough balance to start this battle!", ephemeral=True)
                self.selected_cases = {}
                self.total_bet = 0
            else:
                await self.update_message(interaction)

    @discord.ui.button(label="Bot Battle", style=discord.ButtonStyle.blurple)
    async def bot_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("Only the host can start a bot battle!", ephemeral=True)
        elif len(self.players) > 1:
            await interaction.response.send_message("Can't switch to bot battle after players have joined!", ephemeral=True)
        else:
            modal = BotSelectionModal()
            await interaction.response.send_modal(modal)
            await modal.wait()
            
            if modal.bot_mode:
                self.is_bot_battle = True
                self.bot_mode = modal.bot_mode
                num_bots = int(self.bot_mode[0]) - 1  # Number of bots on the host's team
                self.teams = {
                    1: [self.host] + [self.economy_cog.generate_bot_name() for _ in range(num_bots)],
                    2: [self.economy_cog.generate_bot_name() for _ in range(int(self.bot_mode[0]))]
                }
                await self.update_message(interaction)

    @discord.ui.button(label="Join Battle", style=discord.ButtonStyle.green)
    async def join_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_bot_battle:
            await interaction.response.send_message("This is a bot battle. Players can't join.", ephemeral=True)
        elif not self.selected_cases:
            await interaction.response.send_message("The host hasn't selected cases yet!", ephemeral=True)
        elif interaction.user in self.players:
            await interaction.response.send_message("You've already joined this battle!", ephemeral=True)
        elif len(self.players) >= 8:
            await interaction.response.send_message("This battle is already full!", ephemeral=True)
        else:
            # Check if joining player has enough balance
            if not await self.economy_cog.check_balance(interaction.user, self.total_bet):
                await interaction.response.send_message("You don't have enough balance to join this battle!", ephemeral=True)
                return

            self.players.append(interaction.user)
            if len(self.teams[1]) <= len(self.teams[2]):
                self.teams[1].append(interaction.user)
            else:
                self.teams[2].append(interaction.user)
            await interaction.response.send_message(f"You've joined the battle on Team {1 if interaction.user in self.teams[1] else 2}!", ephemeral=True)
            await self.update_message(interaction)

    @discord.ui.button(label="Start Battle", style=discord.ButtonStyle.danger)
    async def start_battle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("Only the host can start the battle!", ephemeral=True)
        elif not self.selected_cases:
            await interaction.response.send_message("You need to select cases first!", ephemeral=True)
        elif not self.is_bot_battle and len(self.players) < 2:
            await interaction.response.send_message("You need at least 2 players to start the battle!", ephemeral=True)
        else:
            await interaction.response.send_message("Starting the battle!", ephemeral=True)
            self.stop()

    def calculate_total_bet(self):
        return sum(self.case_data[case]['price'] * amount 
                   for case, amount in self.selected_cases.items())

    async def update_message(self, interaction):
        embed = discord.Embed(title="Case Battle", color=discord.Color.gold())
        embed.add_field(name="Host", value=self.host.mention, inline=False)
        
        cases_field = "Selected Cases:\n" + "\n".join(f"{self.case_data[case]['name']}: {amount}" 
                                                      for case, amount in self.selected_cases.items())
        embed.add_field(name="Cases", value=cases_field, inline=False)
        
        embed.add_field(name="Total Bet", value=f"${self.total_bet:,}", inline=False)
        
        players_field = "Players:\n"
        for team_num, team in self.teams.items():
            players_field += f"Team {team_num}: {', '.join(str(player) for player in team)}\n"
        embed.add_field(name="Players", value=players_field, inline=False)
        
        if self.is_bot_battle:
            embed.add_field(name="Mode", value=f"Bot Battle ({self.bot_mode})", inline=False)
        else:
            embed.add_field(name="Mode", value="Player Battle", inline=False)
        
        embed.add_field(name="Status", value="Waiting for case selection and players...", inline=False)
        
        await interaction.message.edit(embed=embed)

class CaseSelectionModal(discord.ui.Modal, title="Select Cases"):
    def __init__(self, case_data):
        super().__init__()
        self.case_data = case_data
        self.selected_cases = {}

        self.case_select = discord.ui.TextInput(
            label="Case Name",
            placeholder="Enter the name of the case",
            required=True
        )
        self.add_item(self.case_select)

        self.quantity_input = discord.ui.TextInput(
            label="Quantity",
            placeholder="Enter a number between 1 and 5",
            min_length=1,
            max_length=1,
            required=True
        )
        self.add_item(self.quantity_input)

    async def on_submit(self, interaction: discord.Interaction):
        selected_case = self.case_select.value.lower()
        try:
            quantity = int(self.quantity_input.value)
            if selected_case not in self.case_data:
                await interaction.response.send_message("Invalid case name. Please try again.", ephemeral=True)
                return

            if 1 <= quantity <= 5:
                if selected_case in self.selected_cases:
                    self.selected_cases[selected_case] += quantity
                else:
                    self.selected_cases[selected_case] = quantity
                
                total_cases = sum(self.selected_cases.values())
                if total_cases > 10:
                    self.selected_cases[selected_case] -= quantity
                    await interaction.response.send_message("You can't select more than 10 cases in total.", ephemeral=True)
                else:
                    await interaction.response.defer()
            else:
                await interaction.response.send_message("Please enter a quantity between 1 and 5.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number for the quantity.", ephemeral=True)



class CaseBattle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.case_data = self.load_case_data()

    def load_case_data(self):
        return {
            "starter_spark": {
                "name": "Starter Spark",
                "price": 500,
                "color": 0x1abc9c,
                "items": {
                    "common": [("Rusty Combat Knife", 75), ("Worn Tactical Vest", 75)],
                    "rare": [("Custom Engraved Pistol", 200), ("Enhanced Night Vision Goggles", 200)],
                    "epic": [("Stealth Recon Outfit", 500), ("Dragonfire Grenade", 500)],
                    "legendary": [("Phoenix Revolver", 1200), ("Spectral Cloak", 1200)]
                }
            },
            "novice_nest": {
                "name": "Novice Nest",
                "price": 1000,
                "color": 0x3498db,
                "items": {
                    "common": [("Basic Survival Gear", 100), ("Entry-Level Drone", 100)],
                    "rare": [("Advanced Sniper Rifle", 300), ("Deployable Shield", 300)],
                    "epic": [("Titanium Combat Armor", 750), ("Quantum Stealth Module", 750)],
                    "legendary": [("Nebula Assault Rifle", 1800), ("Hyperion Battle Suit", 1800)]
                }
            },
            "wanderers_way": {
                "name": "Wanderer's Way",
                "price": 1500,
                "color": 0x9b59b6,
                "items": {
                    "common": [("Standard Issue Handgun", 150), ("Utility Belt", 150)],
                    "rare": [("Exotic Survival Knife", 400), ("Adaptive Camouflage", 400)],
                    "epic": [("Mark II Combat Drone", 900), ("Phantom Suppressor", 900)],
                    "legendary": [("Aurora Energy Blaster", 2200), ("Eclipse Power Armor", 2200)]
                }
            },
            "common_cache": {
                "name": "Common Cache",
                "price": 2000,
                "color": 0xe74c3c,
                "items": {
                    "common": [("Basic Survival Kit", 200), ("Entry-Level Gadget", 200)],
                    "rare": [("Advanced Utility Belt", 500), ("Compact Drone", 500)],
                    "epic": [("Nano-Tech Armor", 1200), ("High-Performance Backpack", 1200)],
                    "legendary": [("Omni-Tool Kit", 3000), ("Elite Tactical Gear", 3000)]
                }
            },
            "cosmic_chest": {
                "name": "Cosmic Chest",
                "price": 3000,
                "color": 0xf39c12,
                "items": {
                    "common": [("Starlight Pendant", 100), ("Galactic Bookmark", 100)],
                    "rare": [("Celestial Map", 300), ("Lunar Lantern", 300)],
                    "epic": [("Nebula Crystal", 700), ("Astral Telescope", 700)],
                    "legendary": [("Quantum Starship Model", 1600), ("Galactic Voyage Diary", 1600)]
                }
            },
            "mystic_box": {
                "name": "Mystic Box",
                "price": 3500,
                "color": 0x8e44ad,
                "items": {
                    "common": [("Enchanted Journal", 150), ("Runic Keychain", 150)],
                    "rare": [("Ancient Rune Stones", 400), ("Mystic Potion Set", 400)],
                    "epic": [("Wizards' Staff Replica", 900), ("Sorcerer's Amulet", 900)],
                    "legendary": [("Arcane Grimoire", 2100), ("Dragon's Heart Crystal", 2100)]
                }
            },
            "futuristic_fortune": {
                "name": "Futuristic Fortune",
                "price": 4000,
                "color": 0x3498db,
                "items": {
                    "common": [("Holo-Glasses", 200), ("Neon Keycard", 200)],
                    "rare": [("Techno Wristband", 500), ("Digital Pet", 500)],
                    "epic": [("Virtual Reality Headset", 1100), ("Holographic Projector", 1100)],
                    "legendary": [("Anti-Gravity Boots", 2500), ("Cybernetic Companion Drone", 2500)]
                }
            },
            "fantasy_bundle": {
                "name": "Fantasy Bundle",
                "price": 4500,
                "color": 0xe74c3c,
                "items": {
                    "common": [("Magic Wand Trinket", 125), ("Fairy Dust Pouch", 125)],
                    "rare": [("Enchanted Necklace", 350), ("Dragon Scale Brooch", 350)],
                    "epic": [("Unicorn Figurine", 800), ("Phoenix Feather Quill", 800)],
                    "legendary": [("Wizard's Cloak", 1900), ("Griffin's Talon", 1900)]
                }
            },
            "retro_vault": {
                "name": "Retro Vault",
                "price": 5000,
                "color": 0xf1c40f,
                "items": {
                    "common": [("Vintage Cassette Tape", 180), ("Retro Game Console Keychain", 180)],
                    "rare": [("Classic Arcade Token Set", 450), ("Old School Action Figure", 450)],
                    "epic": [("Retro Game Cartridge Collection", 1000), ("Vintage Comic Book Collection", 1000)],
                    "legendary": [("Limited Edition Vinyl Record", 2300), ("Retro Gaming Cabinet Model", 2300)]
                }
            },
            "mythic_cache": {
                "name": "Mythic Cache",
                "price": 6000,
                "color": 0x2ecc71,
                "items": {
                    "common": [("Legendary Coin", 200), ("Mystic Amulet", 200)],
                    "rare": [("Ancient Artifact", 500), ("Celestial Pendant", 500)],
                    "epic": [("Elder Relic", 1100), ("Mythic Tome", 1100)],
                    "legendary": [("Godly Crown", 2500), ("Epic Orb of Power", 2500)]
                }
            },
            "celestial_cache": {
                "name": "Celestial Cache",
                "price": 7000,
                "color": 0x34495e,
                "items": {
                    "common": [("Nebula Gem", 250), ("Galactic Scroll", 250)],
                    "rare": [("Solar Flare Pendant", 600), ("Cosmic Ring", 600)],
                    "epic": [("Stellar Map", 1400), ("Astral Compass", 1400)],
                    "legendary": [("Interstellar Telescope", 3200), ("Celestial Artifact", 3200)]
                }
            },
            "arcane_arsenal": {
                "name": "Arcane Arsenal",
                "price": 8000,
                "color": 0x9b59b6,
                "items": {
                    "common": [("Enchanted Mirror", 300), ("Mystic Bracelet", 300)],
                    "rare": [("Arcane Scroll", 750), ("Wizard's Wand", 750)],
                    "epic": [("Sorcerer's Tome", 1700), ("Magical Crystal Ball", 1700)],
                    "legendary": [("Ancient Grimoire", 4000), ("Dragon's Breath Amulet", 4000)]
                }
            },
            "cosmic_conundrum": {
                "name": "Cosmic Conundrum",
                "price": 9000,
                "color": 0x1abc9c,
                "items": {
                    "common": [("Stardust Pendant", 350), ("Galactic Charm", 350)],
                    "rare": [("Lunar Orb", 800), ("Astral Beacon", 800)],
                    "epic": [("Cosmic Map", 1800), ("Nebula Compass", 1800)],
                    "legendary": [("Quantum Starship", 4200), ("Galactic Relic", 4200)]
                }
            },
            "astral_attic": {
                "name": "Astral Attic",
                "price": 10000,
                "color": 0xe67e22,
                "items": {
                    "common": [("Meteorite Fragment", 400), ("Stellar Bookmark", 400)],
                    "rare": [("Solar Prism", 900), ("Lunar Artifact", 900)],
                    "epic": [("Nebula Sphere", 2000), ("Galactic Navigator", 2000)],
                    "legendary": [("Interstellar Capsule", 5000), ("Cosmic Archive", 5000)]
                }
            },
            "infinity_insight": {
                "name": "Infinity Insight",
                "price": 11000,
                "color": 0x3498db,
                "items": {
                    "common": [("Holo-Projector", 450), ("Galactic Token", 450)],
                    "rare": [("Quantum Shard", 1000), ("Celestial Compass", 1000)],
                    "epic": [("Stellar Map", 2200), ("Astral Telescope", 2200)],
                    "legendary": [("Cosmic Relic", 5500), ("Galactic Navigator", 5500)]
                }
            },
            "transcendent_treasure": {
                "name": "Transcendent Treasure",
                "price": 12000,
                "color": 0xf1c40f,
                "items": {
                    "common": [("Cosmic Chip", 500), ("Stellar Key", 500)],
                    "rare": [("Astral Gem", 1100), ("Nebula Pendant", 1100)],
                    "epic": [("Galactic Atlas", 2500), ("Quantum Cube", 2500)],
                    "legendary": [("Celestial Sphere", 6000), ("Ethereal Relic", 6000)]
                }
            },
            "quantum_quiver": {
                "name": "Quantum Quiver",
                "price": 13000,
                "color": 0xe74c3c,
                "items": {
                    "common": [("Lunar Coin", 550), ("Stellar Badge", 550)],
                    "rare": [("Cosmic Lantern", 1200), ("Nebula Map", 1200)],
                    "epic": [("Galactic Telescope", 2800), ("Astral Projector", 2800)],
                    "legendary": [("Interstellar Engine", 6500), ("Quantum Relic", 6500)]
                }
            },
            "omniversal_orb": {
                "name": "Omniversal Orb",
                "price": 14000,
                "color": 0x2ecc71,
                "items": {
                    "common": [("Galactic Fragment", 600), ("Stellar Token", 600)],
                    "rare": [("Astral Compass", 1300), ("Celestial Beacon", 1300)],
                    "epic": [("Nebula Telescope", 3000), ("Cosmic Sphere", 3000)],
                    "legendary": [("Quantum Nexus", 7000), ("Interstellar Artifact", 7000)]
                }
            }
        }

    async def run_battle(self, ctx, battle_message, selected_cases, total_bet, teams, is_bot_battle):
        team_totals = {1: 0, 2: 0}
        player_totals = {player: 0 for team in teams.values() for player in team}

        embed = battle_message.embeds[0]
        embed.set_field_at(-1, name="Battle Progress", value="Opening cases...", inline=False)
        await battle_message.edit(embed=embed)

        for case_type, amount in selected_cases.items():
            for _ in range(amount):
                for team_num, team in teams.items():
                    for player in team:
                        rarity = random.choices(["common", "rare", "epic", "legendary"], weights=[60, 30, 9, 1])[0]
                        item_name, item_value = random.choice(self.case_data[case_type]["items"][rarity])
                        
                        player_totals[player] += item_value
                        team_totals[team_num] += item_value

                        # Update embed
                        progress = "Battle Progress:\n"
                        for t_num, t_total in team_totals.items():
                            progress += f"Team {t_num}: ${t_total:,}\n"
                        embed.set_field_at(-1, name="Battle Progress", value=progress, inline=False)
                        
                        embed.add_field(name=f"{self.case_data[case_type]['name']} Case", 
                                        value=f"{player}: {item_name} (${item_value:,})", 
                                        inline=False)
                        await battle_message.edit(embed=embed)
                        await asyncio.sleep(1)  # Add some delay for suspense

        # Determine winner
        if team_totals[1] > team_totals[2]:
            result = f"Team 1 wins ${total_bet:,}!"
        elif team_totals[1] < team_totals[2]:
            result = f"Team 2 wins ${total_bet:,}!"
        else:
            result = "It's a tie! Bets are returned."

        embed.add_field(name="Result", value=result, inline=False)
        
        # Show individual player totals
        player_results = "Player Totals:\n"
        for player, total in player_totals.items():
            player_results += f"{player}: ${total:,}\n"
        embed.add_field(name="Player Totals", value=player_results, inline=False)
        
        await battle_message.edit(embed=embed)


class SliderGame(View):
    def __init__(self, ctx, economy_cog):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.economy_cog = economy_cog
        self.players = {}
        self.message = None
        self.countdown = 30
        self.max_players = 10
        self.game_ended = False
        self.game_started = False
        self.check_message_task = None
        self.result = None
        self.start_time = None
        self.result_dict = {'🥉': 'Bronze', '🥈': 'Silver', '🥇': 'Gold'}
        self.result_animation = ''

        # Setup buttons
        self.add_item(Button(label="Join Game", style=discord.ButtonStyle.blurple, custom_id="join"))

    async def run_game(self):
        self.message = await self.ctx.send(embed=self.create_embed())
        self.check_message_task = self.check_message_exists.start()
        for i in range(self.countdown, 0, -1):
            self.countdown = i
            await asyncio.sleep(1)
            await self.update_message()
        
        self.game_started = True
        self.start_time = discord.utils.utcnow()
        self.result = await self.generate_result_with_animation()
        await self.process_bets()
        await self.update_message()
        await self.end_game()

    async def generate_result_with_animation(self):
        symbols = ['🥉', '🥈', '🥇']
        weights = [0.45, 0.45, 0.10]  # Probabilities for Bronze, Silver, Gold
        result = random.choices(symbols, weights=weights)[0]
        
        # Create sliding animation
        for _ in range(20):  # Number of animation frames
            animation = [random.choices(symbols, weights)[0] for _ in range(9)]
            self.result_animation = f"{''.join(animation)}\n"
            self.result_animation += "🟦🟦🟦🟦⬆️🟦🟦🟦🟦"
            await self.update_message()
            await asyncio.sleep(0.5)  # Adjust speed of animation
        
        # Final result
        final_animation = [random.choices(symbols, weights)[0] for _ in range(9)]
        final_animation[4] = result  # Put the winning symbol in the middle only for the final result
        self.result_animation = f"{''.join(final_animation)}\n"
        self.result_animation += "🟦🟦🟦🟦⬆️🟦🟦🟦🟦"
        self.result = self.result_dict[result]
        await self.update_message()
        
        return self.result




    async def update_message(self):
        if self.message:
            await self.message.edit(embed=self.create_embed(), view=self)

    async def process_bets(self):
        for player_id, data in self.players.items():
            winnings = 0
            if data['bet_bronze'] > 0 and self.result == "Bronze":
                winnings += data['bet_bronze'] * 2
            if data['bet_silver'] > 0 and self.result == "Silver":
                winnings += data['bet_silver'] * 2
            if data['bet_gold'] > 0 and self.result == "Gold":
                winnings += data['bet_gold'] * 14

            total_bet = data['bet_bronze'] + data['bet_silver'] + data['bet_gold']
            profit = winnings - total_bet
            data['winnings'] = winnings
            data['profit'] = profit

            user_data = await self.economy_cog.get_user_data(player_id)
            user_data['balance'] += winnings  # Add winnings, not profit
            await self.economy_cog.update_user_data(player_id, user_data['balance'], user_data['bank'])

    def create_embed(self):
        if not self.game_started:
            title = "🎰 Slider Game Starting Soon"
            color = discord.Color.blue()
            description = f"```\nGame starts in {self.countdown} seconds\nPlayers: {len(self.players)}/{self.max_players}\n```"
        elif self.result is None:
            title = "🎰 Slider Game in Progress"
            color = discord.Color.gold()
            description = f"```\n{self.result_animation}\n```"
        else:
            title = f"🎰 Slider Game Result: {self.result}"
            color = discord.Color.green()
            description = f"```\n{self.result_animation}\n```"

        embed = discord.Embed(title=title, description=description, color=color)


        for player_id, data in self.players.items():
            player = self.ctx.guild.get_member(player_id)
            total_bet = data['bet_bronze'] + data['bet_silver'] + data['bet_gold']
            bet_colors = []
            if data['bet_bronze'] > 0: bet_colors.append(f"Bronze **({data['bet_bronze']:.2f})**")
            if data['bet_silver'] > 0: bet_colors.append(f"Silver **({data['bet_silver']:.2f})**")
            if data['bet_gold'] > 0: bet_colors.append(f"Gold **({data['bet_gold']:.2f})**")
            
            bet_str = f"**Bet:** ${total_bet:.2f}"
            colors_str = f"**Colors:** {', '.join(bet_colors)}"
            
            if self.result is None:
                status_str = "**Status:** In game"
                profit_str = ""
            else:
                won_colors = [color.split()[0] for color in bet_colors if color.split()[0] == self.result]
                lost_colors = [color.split()[0] for color in bet_colors if color.split()[0] != self.result]
                status_parts = []
                if won_colors:
                    status_parts.append(f"Won: {', '.join(won_colors)}")
                if lost_colors:
                    status_parts.append(f"Lost: {', '.join(lost_colors)}")
                status_str = f"**Status:** {', '.join(status_parts)}"
                profit_str = f"**Profit:** ${data.get('profit', 0):.2f}"

            value = f"{bet_str}\n{colors_str}\n{status_str}\n{profit_str}"
            embed.add_field(name=player.display_name, value=value, inline=False)

        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data["custom_id"] == "join":
            await self.join_game(interaction)
        return True

    async def join_game(self, interaction: discord.Interaction):
        if self.game_started:
            await interaction.response.send_message("The game has already started!", ephemeral=True)
            return
        if self.result is not None:
            await interaction.response.send_message("The game has already ended!", ephemeral=True)
            return
        if len(self.players) >= self.max_players:
            await interaction.response.send_message("The game is full! Please wait for the next round.", ephemeral=True)
            return
        modal = SliderJoinModal(self, interaction.user.id)
        await interaction.response.send_modal(modal)

    async def end_game(self):
        self.game_ended = True
        if self.check_message_task:
            self.check_message_task.cancel()

    @tasks.loop(seconds=5.0)
    async def check_message_exists(self):
        try:
            await self.ctx.fetch_message(self.message.id)
        except discord.NotFound:
            self.game_ended = True
            self.check_message_task.cancel()
            return

    @check_message_exists.before_loop
    async def before_check_message_exists(self):
        await self.bot.wait_until_ready()

class SliderJoinModal(Modal):
    def __init__(self, game, player_id):
        super().__init__(title="Join Slider Game")
        self.game = game
        self.player_id = player_id

        self.add_item(TextInput(label="Bet on Bronze (🥉)", placeholder="Enter amount, 'quarter', 'half', 'all' or leave empty", style=discord.TextStyle.short, required=False))
        self.add_item(TextInput(label="Bet on Silver (🥈)", placeholder="Enter amount, 'quarter', 'half', 'all' or leave empty", style=discord.TextStyle.short, required=False))
        self.add_item(TextInput(label="Bet on Gold (🥇)", placeholder="Enter amount, 'quarter', 'half', 'all' or leave empty", style=discord.TextStyle.short, required=False))

    async def on_submit(self, interaction: discord.Interaction):
        user_data = await self.game.economy_cog.get_user_data(self.player_id)
        current_balance = user_data['balance']

        bets = {}
        total_bet = 0
        special_bets = []

        for item in self.children:
            bet_input = item.value.lower() if item.value else ''
            color = item.label.split()[2].lower()
            if bet_input:
                if bet_input in ['quarter', 'half', 'all']:
                    special_bets.append((color, bet_input))
                else:
                    try:
                        bet = float(bet_input)
                        bets[color] = round(bet, 2)
                        total_bet += bet
                    except ValueError:
                        await interaction.response.send_message(f"Invalid bet value for {item.label}.", ephemeral=True)
                        return

        if len(special_bets) > 2:
            await interaction.response.send_message("You can only use special bets on up to two colors.", ephemeral=True)
            return

        if len(special_bets) == 2:
            colors = [bet[0] for bet in special_bets]
            if 'bronze' in colors and 'silver' in colors:
                await interaction.response.send_message("You can't bet on both Bronze and Silver together.", ephemeral=True)
                return

        total_fraction = 0
        for color, special_bet in special_bets:
            if special_bet == 'quarter':
                fraction = 0.25
            elif special_bet == 'half':
                fraction = 0.5
            else:  # 'all'
                fraction = 1.0
            total_fraction += fraction
            bet_amount = round(current_balance * fraction, 2)
            bets[color] = bet_amount
            total_bet += bet_amount

        if total_fraction > 1:
            await interaction.response.send_message("Your total bet exceeds your balance.", ephemeral=True)
            return

        if len(bets) > 2:
            await interaction.response.send_message("You can only bet on up to two colors.", ephemeral=True)
            return

        if total_bet <= 0:
            await interaction.response.send_message("You must place at least one bet.", ephemeral=True)
            return

        if total_bet > current_balance:
            await interaction.response.send_message("You don't have enough balance for this bet.", ephemeral=True)
            return

        self.game.players[self.player_id] = {
            'bet_bronze': bets.get('bronze', 0),
            'bet_silver': bets.get('silver', 0),
            'bet_gold': bets.get('gold', 0)
        }

        user_data['balance'] = round(user_data['balance'] - total_bet, 2)
        await self.game.economy_cog.update_user_data(self.player_id, user_data['balance'], user_data['bank'])

        await interaction.response.send_message(f"You've joined the game with a total bet of ${total_bet:.2f}", ephemeral=True)
        await self.game.update_message()

class CrashGame(View):
    def __init__(self, ctx, economy_cog):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.economy_cog = economy_cog
        self.multiplier = 1.00
        self.crashed = False
        self.players = {}
        self.crash_point = self.generate_crash_point()
        self.message = None
        self.start_time = None
        self.countdown = 30
        self.max_players = 10
        self.animation_frames = 0
        self.game_ended = False
        self.check_message_task = None

        # Setup buttons
        self.add_item(Button(label="Join Game", style=discord.ButtonStyle.blurple, custom_id="join"))
        self.add_item(Button(label="Cash Out", style=discord.ButtonStyle.green, custom_id="cashout"))

    def generate_crash_point(self):
        # Use a distribution similar to some popular crash games
        r = random.random()
        
        # House edge (adjustable)
        house_edge = 0.02  # 2% house edge
        
        # Calculate crash point
        if r == 0:  # Extremely rare case to prevent division by zero
            return 100.00
        else:
            crash_point = 0.99 / (1 - r)  # This creates a distribution favoring lower numbers
            return max(1.00, round(crash_point, 2))  # Ensure minimum of 1.00

    async def run_game(self):
        self.message = await self.ctx.send(embed=self.create_embed())
        self.check_message_task = self.check_message_exists.start()

        for i in range(self.countdown, 0, -1):
            self.countdown = i
            await asyncio.sleep(1)
            await self.update_message()

        self.start_time = discord.utils.utcnow()

        while self.multiplier < self.crash_point and not self.crashed:
            await asyncio.sleep(0.1)
            self.multiplier = round(self.multiplier + 0.01, 2)
            self.animation_frames += 1
            for player_id, data in self.players.items():
                if not data['cashed_out'] and data['auto_cashout'] and self.multiplier >= data['auto_cashout']:
                    await self.cash_out_player(player_id)
            if self.animation_frames % 5 == 0:  # Update every 0.5 seconds
                await self.update_message()

        self.crashed = True
        for player_id, data in self.players.items():
            if not data['cashed_out']:
                user_data = await self.economy_cog.get_user_data(player_id)
                user_data['balance'] = max(0, user_data['balance'] - data['bet'])
                await self.economy_cog.update_user_data(player_id, user_data['balance'], user_data['bank'])

        await self.update_message()
        await self.end_game()

    @tasks.loop(seconds=5.0)
    async def check_message_exists(self):
        try:
            await self.ctx.channel.fetch_message(self.message.id)
        except discord.NotFound:
            await self.reimburse_players()
            self.check_message_task.cancel()
        except discord.HTTPException:
            pass

    async def reimburse_players(self):
        if self.game_ended:
            return

        for player_id, data in self.players.items():
            if not data['cashed_out']:
                user_data = await self.economy_cog.get_user_data(player_id)
                user_data['balance'] += data['bet']
                await self.economy_cog.update_user_data(player_id, user_data['balance'], user_data['bank'])
                
                player = self.ctx.guild.get_member(player_id)
                if player:
                    try:
                        await player.send(f"The Crash game was unexpectedly ended. Your bet of ${data['bet']:.2f} has been reimbursed.")
                    except discord.HTTPException:
                        pass

        self.game_ended = True

    async def end_game(self):
        self.game_ended = True
        if self.check_message_task:
            self.check_message_task.cancel()

    async def cash_out_player(self, player_id):
        if player_id not in self.players or self.players[player_id]['cashed_out']:
            return

        self.players[player_id]['cashed_out'] = True
        self.players[player_id]['cashout_multiplier'] = self.multiplier
        winnings = self.players[player_id]['bet'] * self.multiplier
        user_data = await self.economy_cog.get_user_data(player_id)
        user_data['balance'] += winnings
        await self.economy_cog.update_user_data(player_id, user_data['balance'], user_data['bank'])

    async def update_message(self):
        await self.message.edit(embed=self.create_embed(), view=self)

    def create_embed(self):
        if not self.start_time:
            title = "🚀 Crash Game Starting Soon"
            color = discord.Color.blue()
            description = f"Game starts in {self.countdown} seconds\nPlayers: {len(self.players)}/{self.max_players}"
        elif self.crashed:
            title = f"💥 Crashed at {self.multiplier}x"
            color = discord.Color.red()
            description = self.generate_rocket_ascii(crashed=True)
        else:
            title = f"🚀 Current Multiplier: {self.multiplier}x"
            color = discord.Color.green()
            description = self.generate_rocket_ascii()

        embed = discord.Embed(title=title, description=f"```\n{description}\n```", color=color)
        
        for player_id, data in self.players.items():
            player = self.ctx.guild.get_member(player_id)
            
            bet_str = f"**Bet:** ${data['bet']:.2f}"
            auto_cashout_str = f"**Auto Cashout:** {data['auto_cashout']}x" if data['auto_cashout'] else "**Auto Cashout:** None"
            
            if data['cashed_out']:
                status = f"Cashed out at {data['cashout_multiplier']}x"
                profit = data['bet'] * (data['cashout_multiplier'] - 1)
                status_str = f"**Status:** {status}"
                profit_str = f"**Profit:** ${profit:.2f}"
            elif self.crashed:
                status_str = "**Status:** Crashed"
                profit_str = f"**Profit:** -${data['bet']:.2f}"
            else:
                status_str = "**Status:** In game"
                if self.start_time:
                    current_profit = data['bet'] * (self.multiplier - 1)
                    profit_str = f"**Profit:** ${current_profit:.2f}"
                else:
                    profit_str = ""

            value = f"{bet_str}\n{auto_cashout_str}\n{status_str}"
            if self.start_time or self.crashed:
                value += f"\n{profit_str}"
            
            embed.add_field(name=player.display_name, value=value, inline=False)

        return embed

    def generate_rocket_ascii(self, crashed=False):
        if crashed:
            return "💥 CRASHED!"
        
        rocket = "🚀"
        trail = "." * (self.animation_frames % 10)
        space = " " * (10 - len(trail))
        return f"{space}{trail}{rocket}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data["custom_id"] == "join":
            await self.join_game(interaction)
        elif interaction.data["custom_id"] == "cashout":
            await self.cash_out(interaction)
        return True

    async def join_game(self, interaction: discord.Interaction):
        if self.start_time:
            await interaction.response.send_message("The game has already started!", ephemeral=True)
            return

        if len(self.players) >= self.max_players:
            await interaction.response.send_message("The game is full! Please wait for the next round.", ephemeral=True)
            return

        modal = CrashJoinModal(self, interaction.user.id)
        await interaction.response.send_modal(modal)

    async def cash_out(self, interaction: discord.Interaction):
        player_id = interaction.user.id
        if player_id not in self.players or self.players[player_id]['cashed_out'] or self.crashed:
            return

        await self.cash_out_player(player_id)
        await self.update_message()
        await interaction.response.defer()

class CrashJoinModal(Modal):
    def __init__(self, game, player_id):
        super().__init__(title="Join Crash Game")
        self.game = game
        self.player_id = player_id

        self.bet = TextInput(label="Bet Amount", placeholder="Enter amount or 'quarter', 'half', 'all'")
        self.auto_cashout = TextInput(label="Auto Cashout (optional)", placeholder="Enter multiplier (e.g., 2 for 2x)", required=False)
        
        self.add_item(self.bet)
        self.add_item(self.auto_cashout)

    async def on_submit(self, interaction: discord.Interaction):
        user_data = await self.game.economy_cog.get_user_data(self.player_id)
        current_balance = user_data['balance']

        try:
            bet_input = self.bet.value.lower()
            if bet_input == 'quarter':
                bet = current_balance / 4
            elif bet_input == 'half':
                bet = current_balance / 2
            elif bet_input == 'all':
                bet = current_balance  # Bet the entire balance
            else:
                bet = float(bet_input)

            bet = round(bet, 2)  # Round to 2 decimal places
            auto_cashout = float(self.auto_cashout.value) if self.auto_cashout.value else None
        except ValueError:
            await interaction.response.send_message("Invalid bet or auto cashout value.", ephemeral=True)
            return

        if bet <= 0:
            await interaction.response.send_message("Bet amount must be positive.", ephemeral=True)
            return

        if bet > current_balance:
            bet = current_balance  # Adjust bet to match current balance if it's somehow higher

        self.game.players[self.player_id] = {
            'bet': bet,
            'auto_cashout': auto_cashout,
            'cashed_out': False,
            'cashout_multiplier': None
        }
        user_data['balance'] -= bet
        await self.game.economy_cog.update_user_data(self.player_id, user_data['balance'], user_data['bank'])

        await interaction.response.send_message(f"You've joined the game with a bet of ${bet:.2f}", ephemeral=True)
        await self.game.update_message()


class TowerGame(View):
    def __init__(self, ctx, bet, economy_cog):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.bet = bet
        self.economy_cog = economy_cog
        self.current_level = 0
        self.max_levels = 10
        self.multipliers = [1.2, 1.5, 1.8, 2.1, 2.5, 3, 3.5, 4, 5, 6]
        self.win_chance = 0.66  # 66% chance to win at each level (2 out of 3 tiles are safe)
        self.towers = [['⬜'] * 10 for _ in range(3)]
        self.safe_tiles = self.generate_safe_tiles()
        self.game_over = False
        self.stopped_at = None
        self.last_safe_level = -1

    def generate_safe_tiles(self):
        return [random.sample(range(3), 2) for _ in range(self.max_levels)]

    @discord.ui.button(label="Left", style=discord.ButtonStyle.blurple)
    async def left(self, interaction: discord.Interaction, button: Button):
        await self.make_move(interaction, 0)

    @discord.ui.button(label="Middle", style=discord.ButtonStyle.blurple)
    async def middle(self, interaction: discord.Interaction, button: Button):
        await self.make_move(interaction, 1)

    @discord.ui.button(label="Right", style=discord.ButtonStyle.blurple)
    async def right(self, interaction: discord.Interaction, button: Button):
        await self.make_move(interaction, 2)

    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.red)
    async def cash_out(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        self.stopped_at = (self.last_safe_level, None)
        await self.end_game(interaction, won=True, cash_out=True)

    async def make_move(self, interaction: discord.Interaction, choice: int):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return

        if choice in self.safe_tiles[self.current_level]:
            self.towers[choice][self.current_level] = '🟩'
            self.last_safe_level = self.current_level
            self.current_level += 1
            if self.current_level == self.max_levels:
                await self.end_game(interaction, won=True)
            else:
                await self.update_message(interaction)
        else:
            self.stopped_at = (self.current_level, choice)
            await self.end_game(interaction, won=False)

    async def update_message(self, interaction):
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def end_game(self, interaction, won, cash_out=False):
        self.game_over = True
        user_id = self.ctx.author.id
        user_data = await self.economy_cog.get_user_data(user_id)

        if won:
            winnings = self.bet * self.multipliers[self.current_level - 1]
            user_data['balance'] += winnings - self.bet
            color = discord.Color.green()
            if cash_out:
                title = f"You Cashed Out at Level {self.current_level}!"
            else:
                title = f"You Reached the Top! Level {self.current_level}"
        else:
            winnings = 0
            user_data['balance'] -= self.bet
            color = discord.Color.red()
            title = f"You Fell at Level {self.current_level + 1}!"

        self.reveal_board()

        await self.economy_cog.update_user_data(user_id, user_data['balance'], user_data['bank'])

        embed = self.create_embed()
        embed.title = title
        embed.color = color
        embed.add_field(name="Result", value=f"You bet **${self.bet:,.2f}** and {'won' if won else 'lost'} **${winnings:,.2f}**.\n"
                                             f"Your new balance is **${user_data['balance']:,.2f}**. 💵", inline=False)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    def reveal_board(self):
        for level in range(self.max_levels):
            for tower in range(3):
                if self.towers[tower][level] == '⬜':
                    if tower in self.safe_tiles[level]:
                        self.towers[tower][level] = '🟩'
                    else:
                        self.towers[tower][level] = '🟥'
        
        if self.stopped_at:
            level, choice = self.stopped_at
            if choice is not None:
                # Player fell
                self.towers[choice][level] = '🟨'
            else:
                # Player cashed out, mark the last safe level
                for tower in range(3):
                    if self.towers[tower][level] == '🟩':
                        self.towers[tower][level] = '🟨'
                        break  # Only mark one tile as yellow

    def create_embed(self):
        tower_display = "".join(f"{''.join(row)}\n" for row in zip(*[tower[::-1] for tower in self.towers]))
        potential_win = self.bet * self.multipliers[self.current_level] if self.current_level < self.max_levels else self.bet * self.multipliers[-1]
        current_win = self.bet * self.multipliers[self.current_level - 1] if self.current_level > 0 else 0
        
        embed = discord.Embed(
            title="Tower Game",
            description=f"**Current Level:** {self.current_level + 1}\n"
                        f"**Potential Win:** ${potential_win:,.2f}\n"
                        f"**Current Win:** ${current_win:,.2f}\n\n"
                        f"```\n{tower_display}```",
            color=discord.Color.blue()
        )
        embed.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)
        
        footer_text = "🟩 = Safe | 🟥 = Bomb | ⬜ = Unknown"
        if self.game_over:
            footer_text += " | 🟨 = Where You Stopped"
        
        embed.set_footer(text=footer_text)
        return embed

class HighLowGame(View):
    def __init__(self, ctx, bet, economy_cog):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.bet = bet
        self.economy_cog = economy_cog
        self.first_number = random.randint(1, 100)
        self.second_number = random.randint(1, 100)

    @discord.ui.button(label="Higher", style=discord.ButtonStyle.green)
    async def higher(self, interaction: discord.Interaction, button: Button):
        await self.make_guess(interaction, "higher")

    @discord.ui.button(label="Lower", style=discord.ButtonStyle.red)
    async def lower(self, interaction: discord.Interaction, button: Button):
        await self.make_guess(interaction, "lower")

    @discord.ui.button(label="Jackpot", style=discord.ButtonStyle.blurple)
    async def jackpot(self, interaction: discord.Interaction, button: Button):
        await self.make_guess(interaction, "jackpot")

    async def make_guess(self, interaction: discord.Interaction, guess):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return

        result = self.check_result(guess)
        await self.end_game(interaction, result)

    def check_result(self, guess):
        if guess == "higher" and self.second_number > self.first_number:
            return "win"
        elif guess == "lower" and self.second_number < self.first_number:
            return "win"
        elif guess == "jackpot" and self.second_number == self.first_number:
            return "jackpot"
        else:
            return "lose"

    async def end_game(self, interaction, result):
        user_id = self.ctx.author.id
        user_data = await self.economy_cog.get_user_data(user_id)
        
        if result == "win":
            winnings = self.bet  # This is the profit
            user_data['balance'] += winnings  # Add only the profit to the balance
            color = discord.Color.green()
            message = f"You won! The number was {self.second_number}."
        elif result == "jackpot":
            winnings = self.bet * 9  # This is the profit (10x bet minus the original bet)
            user_data['balance'] += winnings  # Add only the profit to the balance
            color = discord.Color.gold()
            message = f"JACKPOT! The number was {self.second_number}."
        else:
            winnings = -self.bet  # This is the loss
            user_data['balance'] += winnings  # Subtract the bet from the balance
            color = discord.Color.red()
            message = f"You lost. The number was {self.second_number}."

        await self.economy_cog.update_user_data(user_id, user_data['balance'], user_data['bank'])

        embed = discord.Embed(
            title="Highlow Game Result",
            description=f"First number: {self.first_number}\n{message}\n\n"
                        f"You {'won' if result != 'lose' else 'lost'} **${abs(winnings):,.2f}**.\n"
                        f"Your new balance is **${user_data['balance']:,.2f}**. 💵",
            color=color
        )
        embed.set_author(name=self.ctx.author.display_name, icon_url=self.ctx.author.display_avatar.url)

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)



class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_name = 'economy_database.db'
        self.lock = asyncio.Lock()
        self.db = None
        self.bot.loop.create_task(self.setup_database())
        self.case_data = self.load_case_data()

    def generate_bot_name(self):
        prefixes = ["Cyber", "Quantum", "Nexus", "Astro", "Cosmic", "Nova", "Stellar", "Galactic"]
        suffixes = ["Bot", "AI", "Mind", "Core", "Unit", "Droid", "Sentinel", "Agent"]
        return f"{random.choice(prefixes)}{random.choice(suffixes)}"

    def load_case_data(self):
        return {
            "starter_spark": {
                "name": "Starter Spark",
                "price": 500,
                "color": 0x1abc9c,
                "items": {
                    "common": [("Rusty Combat Knife", 75), ("Worn Tactical Vest", 75)],
                    "rare": [("Custom Engraved Pistol", 200), ("Enhanced Night Vision Goggles", 200)],
                    "epic": [("Stealth Recon Outfit", 500), ("Dragonfire Grenade", 500)],
                    "legendary": [("Phoenix Revolver", 1200), ("Spectral Cloak", 1200)]
                }
            },
            "novice_nest": {
                "name": "Novice Nest",
                "price": 1000,
                "color": 0x3498db,
                "items": {
                    "common": [("Basic Survival Gear", 100), ("Entry-Level Drone", 100)],
                    "rare": [("Advanced Sniper Rifle", 300), ("Deployable Shield", 300)],
                    "epic": [("Titanium Combat Armor", 750), ("Quantum Stealth Module", 750)],
                    "legendary": [("Nebula Assault Rifle", 1800), ("Hyperion Battle Suit", 1800)]
                }
            },
            "wanderers_way": {
                "name": "Wanderer's Way",
                "price": 1500,
                "color": 0x9b59b6,
                "items": {
                    "common": [("Standard Issue Handgun", 150), ("Utility Belt", 150)],
                    "rare": [("Exotic Survival Knife", 400), ("Adaptive Camouflage", 400)],
                    "epic": [("Mark II Combat Drone", 900), ("Phantom Suppressor", 900)],
                    "legendary": [("Aurora Energy Blaster", 2200), ("Eclipse Power Armor", 2200)]
                }
            },
            "common_cache": {
                "name": "Common Cache",
                "price": 2000,
                "color": 0xe74c3c,
                "items": {
                    "common": [("Basic Survival Kit", 200), ("Entry-Level Gadget", 200)],
                    "rare": [("Advanced Utility Belt", 500), ("Compact Drone", 500)],
                    "epic": [("Nano-Tech Armor", 1200), ("High-Performance Backpack", 1200)],
                    "legendary": [("Omni-Tool Kit", 3000), ("Elite Tactical Gear", 3000)]
                }
            },
            "cosmic_chest": {
                "name": "Cosmic Chest",
                "price": 3000,
                "color": 0xf39c12,
                "items": {
                    "common": [("Starlight Pendant", 100), ("Galactic Bookmark", 100)],
                    "rare": [("Celestial Map", 300), ("Lunar Lantern", 300)],
                    "epic": [("Nebula Crystal", 700), ("Astral Telescope", 700)],
                    "legendary": [("Quantum Starship Model", 1600), ("Galactic Voyage Diary", 1600)]
                }
            },
            "mystic_box": {
                "name": "Mystic Box",
                "price": 3500,
                "color": 0x8e44ad,
                "items": {
                    "common": [("Enchanted Journal", 150), ("Runic Keychain", 150)],
                    "rare": [("Ancient Rune Stones", 400), ("Mystic Potion Set", 400)],
                    "epic": [("Wizards' Staff Replica", 900), ("Sorcerer's Amulet", 900)],
                    "legendary": [("Arcane Grimoire", 2100), ("Dragon's Heart Crystal", 2100)]
                }
            },
            "futuristic_fortune": {
                "name": "Futuristic Fortune",
                "price": 4000,
                "color": 0x3498db,
                "items": {
                    "common": [("Holo-Glasses", 200), ("Neon Keycard", 200)],
                    "rare": [("Techno Wristband", 500), ("Digital Pet", 500)],
                    "epic": [("Virtual Reality Headset", 1100), ("Holographic Projector", 1100)],
                    "legendary": [("Anti-Gravity Boots", 2500), ("Cybernetic Companion Drone", 2500)]
                }
            },
            "fantasy_bundle": {
                "name": "Fantasy Bundle",
                "price": 4500,
                "color": 0xe74c3c,
                "items": {
                    "common": [("Magic Wand Trinket", 125), ("Fairy Dust Pouch", 125)],
                    "rare": [("Enchanted Necklace", 350), ("Dragon Scale Brooch", 350)],
                    "epic": [("Unicorn Figurine", 800), ("Phoenix Feather Quill", 800)],
                    "legendary": [("Wizard's Cloak", 1900), ("Griffin's Talon", 1900)]
                }
            },
            "retro_vault": {
                "name": "Retro Vault",
                "price": 5000,
                "color": 0xf1c40f,
                "items": {
                    "common": [("Vintage Cassette Tape", 180), ("Retro Game Console Keychain", 180)],
                    "rare": [("Classic Arcade Token Set", 450), ("Old School Action Figure", 450)],
                    "epic": [("Retro Game Cartridge Collection", 1000), ("Vintage Comic Book Collection", 1000)],
                    "legendary": [("Limited Edition Vinyl Record", 2300), ("Retro Gaming Cabinet Model", 2300)]
                }
            },
            "mythic_cache": {
                "name": "Mythic Cache",
                "price": 6000,
                "color": 0x2ecc71,
                "items": {
                    "common": [("Legendary Coin", 200), ("Mystic Amulet", 200)],
                    "rare": [("Ancient Artifact", 500), ("Celestial Pendant", 500)],
                    "epic": [("Elder Relic", 1100), ("Mythic Tome", 1100)],
                    "legendary": [("Godly Crown", 2500), ("Epic Orb of Power", 2500)]
                }
            },
            "celestial_cache": {
                "name": "Celestial Cache",
                "price": 7000,
                "color": 0x34495e,
                "items": {
                    "common": [("Nebula Gem", 250), ("Galactic Scroll", 250)],
                    "rare": [("Solar Flare Pendant", 600), ("Cosmic Ring", 600)],
                    "epic": [("Stellar Map", 1400), ("Astral Compass", 1400)],
                    "legendary": [("Interstellar Telescope", 3200), ("Celestial Artifact", 3200)]
                }
            },
            "arcane_arsenal": {
                "name": "Arcane Arsenal",
                "price": 8000,
                "color": 0x9b59b6,
                "items": {
                    "common": [("Enchanted Mirror", 300), ("Mystic Bracelet", 300)],
                    "rare": [("Arcane Scroll", 750), ("Wizard's Wand", 750)],
                    "epic": [("Sorcerer's Tome", 1700), ("Magical Crystal Ball", 1700)],
                    "legendary": [("Ancient Grimoire", 4000), ("Dragon's Breath Amulet", 4000)]
                }
            },
            "cosmic_conundrum": {
                "name": "Cosmic Conundrum",
                "price": 9000,
                "color": 0x1abc9c,
                "items": {
                    "common": [("Stardust Pendant", 350), ("Galactic Charm", 350)],
                    "rare": [("Lunar Orb", 800), ("Astral Beacon", 800)],
                    "epic": [("Cosmic Map", 1800), ("Nebula Compass", 1800)],
                    "legendary": [("Quantum Starship", 4200), ("Galactic Relic", 4200)]
                }
            },
            "astral_attic": {
                "name": "Astral Attic",
                "price": 10000,
                "color": 0xe67e22,
                "items": {
                    "common": [("Meteorite Fragment", 400), ("Stellar Bookmark", 400)],
                    "rare": [("Solar Prism", 900), ("Lunar Artifact", 900)],
                    "epic": [("Nebula Sphere", 2000), ("Galactic Navigator", 2000)],
                    "legendary": [("Interstellar Capsule", 5000), ("Cosmic Archive", 5000)]
                }
            },
            "infinity_insight": {
                "name": "Infinity Insight",
                "price": 11000,
                "color": 0x3498db,
                "items": {
                    "common": [("Holo-Projector", 450), ("Galactic Token", 450)],
                    "rare": [("Quantum Shard", 1000), ("Celestial Compass", 1000)],
                    "epic": [("Stellar Map", 2200), ("Astral Telescope", 2200)],
                    "legendary": [("Cosmic Relic", 5500), ("Galactic Navigator", 5500)]
                }
            },
            "transcendent_treasure": {
                "name": "Transcendent Treasure",
                "price": 12000,
                "color": 0xf1c40f,
                "items": {
                    "common": [("Cosmic Chip", 500), ("Stellar Key", 500)],
                    "rare": [("Astral Gem", 1100), ("Nebula Pendant", 1100)],
                    "epic": [("Galactic Atlas", 2500), ("Quantum Cube", 2500)],
                    "legendary": [("Celestial Sphere", 6000), ("Ethereal Relic", 6000)]
                }
            },
            "quantum_quiver": {
                "name": "Quantum Quiver",
                "price": 13000,
                "color": 0xe74c3c,
                "items": {
                    "common": [("Lunar Coin", 550), ("Stellar Badge", 550)],
                    "rare": [("Cosmic Lantern", 1200), ("Nebula Map", 1200)],
                    "epic": [("Galactic Telescope", 2800), ("Astral Projector", 2800)],
                    "legendary": [("Interstellar Engine", 6500), ("Quantum Relic", 6500)]
                }
            },
            "omniversal_orb": {
                "name": "Omniversal Orb",
                "price": 14000,
                "color": 0x2ecc71,
                "items": {
                    "common": [("Galactic Fragment", 600), ("Stellar Token", 600)],
                    "rare": [("Astral Compass", 1300), ("Celestial Beacon", 1300)],
                    "epic": [("Nebula Telescope", 3000), ("Cosmic Sphere", 3000)],
                    "legendary": [("Quantum Nexus", 7000), ("Interstellar Artifact", 7000)]
                }
            }
        }

    async def check_balance(self, user, amount):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER)')
            async with db.execute('SELECT balance FROM users WHERE user_id = ?', (user.id,)) as cursor:
                result = await cursor.fetchone()
            
            if result is None:
                await db.execute('INSERT INTO users (user_id, balance) VALUES (?, 0)', (user.id,))
                await db.commit()
                return False
            
            return result[0] >= amount

    async def setup_database(self):
        self.db = await aiosqlite.connect(self.db_name)
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS user_data (
                user_id INTEGER PRIMARY KEY,
                balance REAL,
                bank REAL
            )
        ''')
        await self.db.commit()

    async def get_user_data(self, user_id: int):
        async with self.lock:
            async with self.db.execute('SELECT balance, bank FROM user_data WHERE user_id = ?', (user_id,)) as cursor:
                result = await cursor.fetchone()
                if result:
                    return {'balance': result[0], 'bank': result[1]}
                else:
                    return {'balance': 0, 'bank': 0}

    async def update_user_data(self, user_id: int, new_balance: float, new_bank: float):
        async with self.lock:
            new_balance = round(max(0, new_balance), 2)
            new_bank = round(max(0, new_bank), 2)
            await self.db.execute('''
                INSERT OR REPLACE INTO user_data (user_id, balance, bank)
                VALUES (?, ?, ?)
            ''', (user_id, new_balance, new_bank))
            await self.db.commit()

    async def send_embed(self, ctx, description: str, color: discord.Color, delete_after: int = None):
        embed = discord.Embed(description=description, color=color)
        message = await ctx.send(embed=embed)
        if delete_after:
            await message.delete(delay=delete_after)

    def cog_unload(self):
        asyncio.create_task(self.close_db())

    async def close_db(self):
        if self.db:
            await self.db.close()


    @commands.command(aliases=['cb'])
    async def casebattle(self, ctx):
        embed = discord.Embed(title="Case Battle", color=discord.Color.gold())
        
        embed.add_field(name="Host", value=ctx.author.mention, inline=False)
        embed.add_field(name="Cases", value="Not selected yet", inline=False)
        embed.add_field(name="Total Bet", value="$0", inline=False)
        embed.add_field(name="Players", value="Waiting for players to join...", inline=False)
        embed.add_field(name="Mode", value="Player Battle", inline=False)
        embed.add_field(name="Status", value="Waiting for case selection and players...", inline=False)
        
        view = CaseBattleView(ctx.author, self, self.case_data)  # Pass self.case_data here
        message = await ctx.send(embed=embed, view=view)
        
        await view.wait()
        
        if view.selected_cases:
            await self.run_battle(ctx, message, view.selected_cases, view.total_bet, view.teams, view.is_bot_battle)
        else:
            embed.set_field_at(5, name="Status", value="Battle cancelled - no cases selected", inline=False)
            await message.edit(embed=embed, view=None)


    async def run_battle(self, ctx, battle_message, selected_cases, total_bet, teams, is_bot_battle):
        embed = battle_message.embeds[0]
        team_totals = {1: 0, 2: 0}
        player_totals = {player: 0 for team in teams.values() for player in team}

        embed.set_field_at(5, name="Status", value="Opening cases...", inline=False)
        await battle_message.edit(embed=embed)

        for case_type, amount in selected_cases.items():
            for _ in range(amount):
                for team_num, team in teams.items():
                    for player in team:
                        rarity = random.choices(["common", "rare", "epic", "legendary"], weights=[60, 30, 9, 1])[0]
                        item_name, item_value = random.choice(self.case_data[case_type]["items"][rarity])
                        
                        player_totals[player] += item_value
                        team_totals[team_num] += item_value

                        progress = "Battle Progress:\n"
                        for t_num, t_total in team_totals.items():
                            progress += f"Team {t_num}: ${t_total:,}\n"
                        embed.set_field_at(5, name="Status", value=progress, inline=False)
                        
                        embed.add_field(name=f"{self.case_data[case_type]['name']} Case", 
                                        value=f"{player}: {item_name} (${item_value:,})", 
                                        inline=False)
                        await battle_message.edit(embed=embed)
                        await asyncio.sleep(1)  # Add some delay for suspense

        # Determine winner
        if team_totals[1] > team_totals[2]:
            result = f"Team 1 wins ${total_bet:,}!"
        elif team_totals[1] < team_totals[2]:
            result = f"Team 2 wins ${total_bet:,}!"
        else:
            result = "It's a tie! Bets are returned."

        embed.add_field(name="Result", value=result, inline=False)
        
        # Show individual player totals
        player_results = "Player Totals:\n"
        for player, total in player_totals.items():
            player_results += f"{player}: ${total:,}\n"
        embed.add_field(name="Player Totals", value=player_results, inline=False)
        
        # Update player balances based on the results
        winning_team = 1 if team_totals[1] > team_totals[2] else 2
        losing_team = 2 if winning_team == 1 else 1

        async with aiosqlite.connect('your_database.db') as db:
            if team_totals[1] != team_totals[2]:  # If it's not a tie
                for player in teams[winning_team]:
                    if not isinstance(player, str):  # Check if it's not a bot
                        await db.execute(
                            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                            (total_bet // len(teams[winning_team]), player.id)
                        )
                
                for player in teams[losing_team]:
                    if not isinstance(player, str):  # Check if it's not a bot
                        await db.execute(
                            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
                            (total_bet // len(teams[losing_team]), player.id)
                        )
            else:
                # If it's a tie, return the bets
                for team in teams.values():
                    for player in team:
                        if not isinstance(player, str):  # Check if it's not a bot
                            await db.execute(
                                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                                (total_bet // (len(teams[1]) + len(teams[2])), player.id)
                            )
            
            await db.commit()

            # Update the embed to show the new balances
            for team_num, team in teams.items():
                for player in team:
                    if not isinstance(player, str):  # Check if it's not a bot
                        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (player.id,)) as cursor:
                            result = await cursor.fetchone()
                            new_balance = result[0] if result else 0
                        embed.add_field(name=f"{player} New Balance", value=f"${new_balance:,}", inline=True)

        await battle_message.edit(embed=embed)



    @commands.command()
    async def slider(self, ctx):
        game = SliderGame(ctx, self)
        await game.run_game()

    @commands.command(name='balance', description='Check your balance or the balance of another user.', aliases=['bal', 'money', 'cash', 'bank', 'wallet', 'networth'])
    async def balance(self, ctx, member: discord.Member = None):
        if member is None:
            user_id = ctx.author.id
            user_data = await self.get_user_data(user_id)
            user = ctx.author
        else:
            user_id = member.id
            user_data = await self.get_user_data(user_id)
            user = member

        balance = user_data['balance']
        bank = user_data['bank']
        networth = balance + bank

        await self.send_embed(ctx, f"🏦 {user.mention}, **Wallet**: ${balance:,.2f}, **Bank**: ${bank:,.2f}, **Networth**: ${networth:,.2f}", 0x747c8c)

    @commands.command(name='deposit', description='Deposit dollars into your bank.', aliases=['dep', 'depo'])
    async def deposit(self, ctx, amount: str):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        if amount.lower() == 'half':
            amount = user_data['balance'] / 2
        elif amount.lower() == 'all':
            amount = user_data['balance']
        elif amount.lower() == 'quarter':
            amount = user_data['balance'] / 4
        else:
            try:
                amount = float(amount)
            except ValueError:
                await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", discord.Color.red(), delete_after=5)
                return

        if amount <= 0:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You must deposit a positive amount.", discord.Color.red(), delete_after=5)
            return

        if user_data['balance'] < amount:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You do not have enough dollars to deposit.", discord.Color.red(), delete_after=5)
            return

        user_data['balance'] -= amount
        user_data['bank'] += amount
        await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

        await self.send_embed(ctx, f"🏦 {ctx.author.mention}, **Amount Deposited**: ${amount:,.2f}", discord.Color.green(), delete_after=5)

    @commands.command(name='withdraw', description='Withdraw dollars from your bank.', aliases=['with', 'bankwithdraw'])
    async def withdraw(self, ctx, amount: str):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        if amount.lower() == 'half':
            amount = user_data['bank'] / 2
        elif amount.lower() == 'all':
            amount = user_data['bank']
        elif amount.lower() == 'quarter':
            amount = user_data['bank'] / 4
        else:
            try:
                amount = float(amount)
            except ValueError:
                await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", discord.Color.red(), delete_after=5)
                return

        if amount <= 0:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You must withdraw a positive amount.", discord.Color.red(), delete_after=5)
            return

        if user_data['bank'] < amount:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You do not have enough money in the bank to withdraw.", discord.Color.red(), delete_after=5)
            return

        user_data['balance'] += amount
        user_data['bank'] -= amount
        await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

        await self.send_embed(ctx, f"🏦 {ctx.author.mention}, **Amount Withdrawn**: ${amount:,.2f}", discord.Color.green(), delete_after=5)



    @commands.command(name='beg', description='Beg for money.')
    @commands.cooldown(1, 30, commands.BucketType.user)  # 30 second cooldown
    async def beg(self, ctx):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        celebrities = [
            "Elon Musk", "Jeff Bezos", "Bill Gates", "Mark Zuckerberg", "Kanye West", 
            "Drake", "Rihanna", "Taylor Swift", "PewDiePie", "MrBeast", "Ninja", 
            "Jacksepticeye", "Kylie Jenner", "Ariana Grande", "Justin Bieber", "Cardi B", 
            "Travis Scott", "Lil Nas X", "Selena Gomez", "Zendaya", "Logan Paul", 
            "Jake Paul", "Shane Dawson", "James Charles", "Snoop Dogg", "Eminem", 
            "Nicki Minaj", "Lil Wayne", "Kendrick Lamar", "Migos", "Post Malone", 
            "Your Mom", "Gordon Ramsay", "Oprah Winfrey", "Ellen DeGeneres", 
            "Your Sister", "Fanum", "Jimmy Kimmel", "Your Brother", 
            "Cristiano Ronaldo", "LeBron James", "Tom Brady", "Michael Jackson", 
            "Usain Bolt", "Kim Kardashian", "Dwayne Johnson", "Ryan Reynolds", 
            "Jason Momoa", "Kevin Hart", "Henry Cavill", "Margot Robbie", 
            "Timothée Chalamet", "Andrew Tate", "Robert Downey Jr.", 
            "Kai Cenat", "Chris Hemsworth", "Tom Holland", 
            "Johnny Depp", "Angelina Jolie", "Brad Pitt", "Matthew McConaughey",
            "Will Smith", "Jada Pinkett Smith", "Javier Bardem", "Duke Dennis",
            "Beyoncé", "Adele", "Shakira", "Miley Cyrus", "Jesus Christ", "Zayn Malik", 
            "Ed Sheeran", "Sam Smith", "Halsey", "Post Malone", "Doja Cat", 
            "Halsey", "The Weeknd", "Megan Thee Stallion", "Billie Eilish", 
            "J Cole", "Drake", "Lil Uzi Vert", "Future", "Tyler, The Creator", 
            "SZA", "A$AP Rocky", "Travis Scott", "Juice WRLD", "21 Savage"
        ]

        scenarios = [
            "You begged and received **${:,.2f}** from **{}**. Say thank you!",
            "You begged and found **${:,.2f}** on the ground.",
            "You begged and a generous person gave you **${:,.2f}**.",
            "You begged and found a hidden stash of **${:,.2f}**.",
            "You begged and **{}** gave you **${:,.2f}**.",
            "You begged **{}** and they were feeling generous and gave you **${:,.2f}**.",
            "You begged and **Random Stranger** gave you **${:,.2f}**.",
            "You begged **{}** and they gave you **${:,.2f}**.",
            "You begged **{}** and they gave you **${:,.2f}**. They said you might have better luck next time.",
            "You begged **{}** and they gave you **${:,.2f}** and some advice on how to improve your begging skills.",
            "You begged and **{}** was in a good mood, so they gave you **${:,.2f}**.",
            "You begged and **{}** was so impressed by your persistence that they gave you **${:,.2f}**.",
            "You begged **{}** and they gave you **${:,.2f}** because they felt sorry for you.",
            "You begged **{}** and they gave you **${:,.2f}** as a reward for your efforts.",
            "You begged **{}** and they generously gave you **${:,.2f}**.",
            "You begged **{}** and they gave you **${:,.2f}** along with some motivational words.",
            "You begged **{}** and they gave you **${:,.2f}**. They said, 'Keep going!'",
            "You begged and **{}** decided to help you out with **${:,.2f}**.",
            "You begged and **{}** gave you **${:,.2f}** because they liked your determination.",
            "You begged and **{}** gave you **${:,.2f}** after you told them your story.",
            "You begged **{}** and they gave you **${:,.2f}**. They wished you good luck!",
            "You begged **{}** and they gave you **${:,.2f}** and said to pass it on when you can.",
            "You begged **{}** and they gave you **${:,.2f}**. They were impressed by your perseverance.",
            "You begged **{}** and they gave you **${:,.2f}** and a smile.",
            "You begged **{}** for money and they gave you a **${:,.2f}** gift card instead.",
            "You begged **{}** and they gave you **${:,.2f}** to help with your situation.",
            "You begged **{}** but they said they couldn’t help today.",
            "You begged **{}** and they were not in the mood to give.",
            "You begged **{}** and they told you to try asking someone else.",
            "You begged **{}** and they said they’re out of cash.",
            "You begged **{}** and they gave you a pep talk but no money.",
            "You begged **{}** but they just walked away without saying a word.",
            "You begged **{}** and they told you to get a job instead.",
            "You begged **{}** and they gave you a discount coupon instead.",
            "You begged **{}** and they said they had no money to spare.",
            "You begged **{}** and they told you to try your luck elsewhere.",
            "You begged **{}** but they were not interested in helping."
        ]

        scenario = random.choice(scenarios)
        if "{}" in scenario:
            if "received" in scenario or "found" in scenario or "gave you" in scenario:
                amount = random.uniform(10, 500)
                user_data['balance'] += amount
                await self.update_user_data(user_id, user_data['balance'], user_data['bank'])
                if "Random Stranger" in scenario:
                    scenario = scenario.format(amount)
                else:
                    celebrity = random.choice(celebrities)
                    scenario = scenario.format(celebrity, amount)
            else:
                celebrity = random.choice(celebrities)
                scenario = scenario.format(celebrity)
        else:
            scenario = scenario.format(random.choice(celebrities))  # For scenarios that don't need an amount

        # Format the amount in the message if present
        scenario = scenario.replace("{amount:,.2f}", f"{amount:,.2f}")

        await self.send_embed(ctx, f"🤲 {ctx.author.mention}, {scenario}", discord.Color.yellow())




    @commands.command(name='search', description='Search for items or money.')
    @commands.cooldown(1, 60, commands.BucketType.user)  # 1 minute cooldown
    async def search(self, ctx):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        scenarios = [
            "You searched the local trash can and found **${:,.2f}**.",
            "You searched under the couch and found **${:,.2f}**.",
            "You searched the park and found a hidden treasure of **${:,.2f}**.",
            "You searched the alley and found **${:,.2f}** in an old wallet.",
            "You searched the dumpster and found **${:,.2f}** in a discarded bag.",
            "You searched the old bookstore and found **${:,.2f}** in a forgotten book.",
            "You searched the abandoned warehouse and discovered **${:,.2f}** in a hidden compartment.",
            "You searched the beach and stumbled upon **${:,.2f}** in a buried chest.",
            "You searched the attic and found **${:,.2f}** in a dusty old trunk.",
            "You searched the park bench and found **${:,.2f}** stuffed between the cushions.",
            "You searched the train station and discovered **${:,.2f}** in an old suitcase.",
            "You searched the library and found **${:,.2f}** in a misplaced book.",
            "You searched the carnival and stumbled upon **${:,.2f}** in a forgotten game booth.",
            "You searched the abandoned mall and discovered **${:,.2f}** in a broken vending machine.",
            "You searched the old theater and found **${:,.2f}** in a hidden drawer.",
            "You searched the old circus tent and found **${:,.2f}** in a forgotten box.",
            "You searched the zoo and discovered **${:,.2f}** hidden behind the animal enclosure.",
            "You searched the museum and found **${:,.2f}** in a hidden display.",
            "You searched the hospital and stumbled upon **${:,.2f}** in an old donation box.",
            "You searched the police station and found **${:,.2f}** in a lost and found box.",
            "You searched the airport and discovered **${:,.2f}** in abandoned luggage.",
            "You searched the college campus and found **${:,.2f}** in a forgotten locker.",
            "You searched the amusement park and discovered **${:,.2f}** in a broken ride.",
            "You searched the farmers' market and found **${:,.2f}** in a misplaced produce crate.",
            "You searched the botanical garden and found **${:,.2f}** in a hidden plant pot.",
            "You searched the abandoned factory and discovered **${:,.2f}** in a dusty crate.",
            "You searched the historical monument and found **${:,.2f}** in a hidden alcove.",
            "You searched the old library and found **${:,.2f}** in a secret compartment.",
            "You searched the hiking trail and stumbled upon **${:,.2f}** buried in a cave.",
            "You searched the construction site and discovered **${:,.2f}** in an old tool box.",
            "You searched the marina and found **${:,.2f}** in a sunken boat.",
            "You searched the stadium and discovered **${:,.2f}** in a forgotten concession stand.",
            "You searched the old diner and found **${:,.2f}** in a hidden drawer.",
            "You searched the abandoned amusement park and discovered **${:,.2f}** in an old ticket booth.",
            "You searched the parking garage and found **${:,.2f}** in a discarded parking ticket.",
            "You searched the botanical garden and discovered **${:,.2f}** in a hidden garden gnome.",
            "You searched the local gym and found **${:,.2f}** in an abandoned locker.",
            "You searched the historic battlefield and discovered **${:,.2f}** buried in the ground.",
            "You searched the city aquarium and found **${:,.2f}** in an old fish tank.",
            "You searched the rooftop and discovered **${:,.2f}** in a hidden container.",
            "You searched the ancient ruins and found **${:,.2f}** in a hidden chamber."
        ]

        scenario = random.choice(scenarios)
        if "found" in scenario or "discovered" in scenario:
            amount = random.uniform(10, 500)
            user_data['balance'] += amount
            await self.update_user_data(user_id, user_data['balance'], user_data['bank'])
            scenario = scenario.format(amount)

        await self.send_embed(ctx, f"🔍 {ctx.author.mention}, {scenario}", discord.Color.blue())

    @commands.command(name='daily', description='Claim a daily reward.')
    async def daily(self, ctx):
        user_id = ctx.author.id
        current_time = int(time.time())
        cooldown_end = await self.db.get_cooldown(user_id, 'daily')

        if cooldown_end and current_time < cooldown_end:
            remaining_time = cooldown_end - current_time
            await self.send_embed(ctx, f"🕐 {ctx.author.mention}, **Error**: You need to wait {remaining_time} seconds before you can claim your daily reward again.", discord.Color.yellow(), delete_after=5)
            return

        user_data = await self.get_user_data(user_id)
        reward_amount = random.uniform(100, 500)
        user_data['balance'] += reward_amount
        await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

        # Set cooldown
        await self.db.set_cooldown(user_id, 'daily', current_time + 86400)  # 24 hours cooldown

        await self.send_embed(ctx, f"💸 {ctx.author.mention}, **Claimed**: ${reward_amount:,.2f} as your daily reward!", discord.Color.yellow())

    @commands.command(name='weekly', description='Claim a weekly reward.')
    async def weekly(self, ctx):
        user_id = ctx.author.id
        current_time = int(time.time())
        cooldown_end = await self.db.get_cooldown(user_id, 'weekly')

        if cooldown_end and current_time < cooldown_end:
            remaining_time = cooldown_end - current_time
            await self.send_embed(ctx, f"🕐 {ctx.author.mention}, **Error**: You need to wait {remaining_time} seconds before you can claim your weekly reward again.", discord.Color.yellow(), delete_after=5)
            return

        user_data = await self.get_user_data(user_id)
        reward_amount = random.uniform(500, 2000)
        user_data['balance'] += reward_amount
        await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

        # Set cooldown
        await self.db.set_cooldown(user_id, 'weekly', current_time + 604800)  # 7 days cooldown

        await self.send_embed(ctx, f"💰 {ctx.author.mention}, **Claimed**: ${reward_amount:,.2f} as your weekly reward!", discord.Color.yellow())

    @commands.command(name='monthly', description='Claim a monthly reward.')
    async def monthly(self, ctx):
        user_id = ctx.author.id
        current_time = int(time.time())
        cooldown_end = await self.db.get_cooldown(user_id, 'monthly')

        if cooldown_end and current_time < cooldown_end:
            remaining_time = cooldown_end - current_time
            await self.send_embed(ctx, f"🕐 {ctx.author.mention}, **Error**: You need to wait {remaining_time} seconds before you can claim your monthly reward again.", discord.Color.yellow(), delete_after=5)
            return

        user_data = await self.get_user_data(user_id)
        reward_amount = random.uniform(2000, 5000)
        user_data['balance'] += reward_amount
        await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

        # Set cooldown
        await self.db.set_cooldown(user_id, 'monthly', current_time + 2592000)  # 30 days cooldown

        await self.send_embed(ctx, f"💵 {ctx.author.mention}, **Claimed**: ${reward_amount:,.2f} as your monthly reward!", discord.Color.yellow())



    @commands.command(name='crime', aliases=['heist'], description='Commit a crime and potentially gain or lose money.')
    async def crime(self, ctx):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)
        balance = user_data['balance']

        # List of 50 possible outcomes and their impact on balance
        scenarios = [
            ("You successfully robbed a bank and got away with **${:,.2f}**!", 0.5),
            ("You managed to steal **${:,.2f}** from a wealthy businessman!", 0.4),
            ("You pulled off a daring heist and got **${:,.2f}**!", 0.35),
            ("You raided a jewelry store and found **${:,.2f}**!", 0.3),
            ("You picked the lock and nabbed **${:,.2f}**!", 0.25),
            ("You sneaked into a casino and won **${:,.2f}**!", 0.2),
            ("You looted a rich person's house and found **${:,.2f}**!", 0.15),
            ("You intercepted a money truck and seized **${:,.2f}**!", 0.4),
            ("You managed a small-time robbery and got **${:,.2f}**!", 0.1),
            ("You lifted some cash from a street vendor and ended up with **${:,.2f}**!", 0.05),
            ("You successfully stole **${:,.2f}** from a high-end boutique!", 0.3),
            ("You picked up **${:,.2f}** from a petty theft!", 0.1),
            ("You swiped **${:,.2f}** from a careless wallet snatcher!", 0.2),
            ("You jacked **${:,.2f}** from a local bank!", 0.35),
            ("You snagged **${:,.2f}** from a gambling den!", 0.25),
            ("You scored **${:,.2f}** from an ATM heist!", 0.4),
            ("You nabbed **${:,.2f}** from a convenience store!", 0.1),
            ("You pulled off a successful burglary and got **${:,.2f}**!", 0.3),
            ("You got away with **${:,.2f}** after a quick smash-and-grab!", 0.2),
            ("You robbed a high-roller and scored **${:,.2f}**!", 0.35),
            ("You got **${:,.2f}** from a poker game heist!", 0.3),
            ("You snagged **${:,.2f}** from a museum robbery!", 0.4),
            ("You scored **${:,.2f}** from a successful shoplifting!", 0.15),
            ("You managed to grab **${:,.2f}** from a wealthy benefactor!", 0.25),
            ("You acquired **${:,.2f}** from a daring pickpocket!", 0.1),
            ("You came away with **${:,.2f}** from a risky burglary!", 0.3),
            ("You snatched **${:,.2f}** from a pawn shop!", 0.2),
            ("You lifted **${:,.2f}** from an unsuspecting shopper!", 0.1),
            ("You scored **${:,.2f}** from a lavish party!", 0.4),
            ("You managed to rob a casino and got **${:,.2f}**!", 0.35),
            ("You pulled in **${:,.2f}** from a well-planned heist!", 0.3),
            ("You seized **${:,.2f}** from a daring safe-crack!", 0.2),
            ("You snatched **${:,.2f}** from an elite club!", 0.15),
            ("You robbed a rich mansion and walked away with **${:,.2f}**!", 0.4),
            ("You grabbed **${:,.2f}** from an abandoned warehouse!", 0.25),
            ("You scored **${:,.2f}** from a successful carjacking!", 0.1),
            ("You netted **${:,.2f}** from a quick stick-up!", 0.35),
            ("You successfully heisted **${:,.2f}** from a tech mogul!", 0.3),
            ("You nabbed **${:,.2f}** from a high-stakes poker game!", 0.4),
            ("You acquired **${:,.2f}** from an upscale mall!", 0.25),
            ("You stole **${:,.2f}** from a big-shot entrepreneur!", 0.35),
            ("You lifted **${:,.2f}** from a luxury apartment!", 0.3),
            ("You seized **${:,.2f}** from a diamond store!", 0.4),
            ("You made off with **${:,.2f}** from a quick robbery!", 0.2),
            ("You grabbed **${:,.2f}** from a high-end restaurant!", 0.3),
            ("You successfully pilfered **${:,.2f}** from a casino vault!", 0.35),
            ("You snagged **${:,.2f}** from a rich celebrity!", 0.4),
            ("You came away with **${:,.2f}** from a wealthy patron!", 0.25),
            ("You scored **${:,.2f}** from a risky theft!", 0.3),
            ("You nabbed **${:,.2f}** from a busy marketplace!", 0.15),
            ("You pulled in **${:,.2f}** from a daring robbery!", 0.35),
            ("You stole **${:,.2f}** from a high-end auction!", 0.4),
            ("You acquired **${:,.2f}** from a quick stick-up!", 0.25),
            ("You lifted **${:,.2f}** from a large warehouse!", 0.3),
            ("You successfully pilfered **${:,.2f}** from a luxury yacht!", 0.35),
            ("You managed to snag **${:,.2f}** from a major heist!", 0.4),
            ("You scored **${:,.2f}** from a successful burglary!", 0.3),
            ("You grabbed **${:,.2f}** from a lavish event!", 0.35),
            ("You successfully lifted **${:,.2f}** from a rich philanthropist!", 0.4),
            ("You were caught during the robbery and fined **${:,.2f}**!", -0.5),
            ("You attempted a heist but got nothing and lost **${:,.2f}** in legal fees!", -0.35),
            ("You were apprehended and lost **${:,.2f}** to the authorities!", -0.4),
            ("You failed the crime and lost **${:,.2f}** to your accomplices!", -0.3),
            ("You got caught and had to pay **${:,.2f}** in damages!", -0.25),
            ("You attempted a robbery but ended up with a **${:,.2f}** fine!", -0.2),
            ("You were unsuccessful and **${:,.2f}** was stolen from you by others!", -0.15),
            ("You botched the crime and lost **${:,.2f}** in bribes!", -0.1),
            ("You were caught in the act and **${:,.2f}** was confiscated!", -0.35),
            ("Your crime failed miserably and you owe **${:,.2f}** in repairs!", -0.4),
            ("You attempted a crime but ended up in jail, losing **${:,.2f}**!", -0.5),
            ("Your heist was a flop and you lost **${:,.2f}** to the police!", -0.3),
            ("You failed and had to cover **${:,.2f}** in damages!", -0.25),
            ("You got caught trying to rob a bank and lost **${:,.2f}**!", -0.4),
            ("Your crime was unsuccessful and you lost **${:,.2f}** to legal fees!", -0.35),
            ("You were arrested and had to pay **${:,.2f}** in fines!", -0.3),
            ("Your robbery failed and you had to cover **${:,.2f}** in damages!", -0.25),
            ("You attempted a robbery and lost **${:,.2f}** to the cops!", -0.4),
            ("Your crime went awry and you lost **${:,.2f}** in bribes!", -0.35),
            ("You were unsuccessful and **${:,.2f}** was taken from you by rivals!", -0.3),
            ("You got caught and had to pay **${:,.2f}** in legal costs!", -0.25),
            ("You tried a robbery but ended up with **${:,.2f}** in fines!", -0.4),
            ("You failed and **${:,.2f}** was seized by the authorities!", -0.3),
            ("You were apprehended and lost **${:,.2f}** to legal issues!", -0.35),
            ("You botched the heist and had to pay **${:,.2f}** in fines!", -0.2),
            ("Your robbery failed and you lost **${:,.2f}** to damages!", -0.25),
            ("You attempted a crime but had to pay **${:,.2f}** in compensation!", -0.3),
            ("Your crime was unsuccessful and you lost **${:,.2f}** in bribes!", -0.4),
            ("You were caught and had to pay **${:,.2f}** in legal fees!", -0.35),
            ("You failed the robbery and lost **${:,.2f}** to the police!", -0.4),
            ("Your heist went wrong and you lost **${:,.2f}** in damages!", -0.3),
            ("You attempted a robbery and ended up with **${:,.2f}** in fines!", -0.25),
        ]

        # Minimum gain amount for successful crimes
        min_gain = 50  # Minimum gain amount in dollars

        # Select a random outcome
        outcome, multiplier = random.choice(scenarios)

        # Determine gain or loss
        if multiplier > 0:
            if balance == 0:
                gain = min_gain  # Ensure minimum gain if balance is 0
            else:
                gain = balance * multiplier
            user_data['balance'] += gain
            embed_title = f"You Gained ${gain:,.2f}!"
            embed_color = discord.Color.green()
        elif multiplier < 0:
            if balance == 0:
                loss = 0  # No loss if balance is 0
            else:
                loss = abs(balance * multiplier)
            user_data['balance'] -= loss
            embed_title = f"You Lost ${loss:,.2f}!"
            embed_color = discord.Color.red()
        else:
            embed_title = "Nothing Happened"
            embed_color = discord.Color.gray()

        await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

        # Send feedback message
        await self.send_embed(ctx, f"💰{ctx.author.mention}, {outcome.format(gain if multiplier > 0 else loss)}\nYour current balance is **${user_data['balance']:,.2f}**.", embed_color)


    @commands.command(name='highlow', aliases=['hl'], description='Play the Highlow game.')
    async def highlow(self, ctx, amount: str):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        if amount.lower() == 'half':
            amount = user_data['balance'] / 2
        elif amount.lower() == 'all':
            amount = user_data['balance']
        elif amount.lower() == 'quarter':
            amount = user_data['balance'] / 4
        else:
            try:
                amount = float(amount)
            except ValueError:
                await ctx.send(f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", delete_after=5)
                return

        if amount <= 0:
            await ctx.send(f"🚫 {ctx.author.mention}, **Error**: You must bet a positive amount.", delete_after=5)
            return

        if user_data['balance'] < amount:
            await ctx.send(f"🚫 {ctx.author.mention}, **Error**: You do not have enough dollars to bet.", delete_after=5)
            return

        game = HighLowGame(ctx, amount, self)
        embed = discord.Embed(
            title="Highlow Game",
            description=f"The number is **{game.first_number}**.\n"
                        f"Will the next number be higher, lower, or the same?\n"
                        f"Your bet: **${amount:,.2f}**",
            color=discord.Color.blue()
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed, view=game)

    @highlow.error
    async def highlow_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", delete_after=5)

    @commands.command(name='crash', description='Start a Crash game.')
    async def crash(self, ctx):
        game = CrashGame(ctx, self)
        await game.run_game()

    @crash.error
    async def crash_error(self, ctx, error):
        await ctx.send(f"🚫 {ctx.author.mention}, **Error**: An error occurred while starting the game.", delete_after=5)





    @commands.command(name='tower', description='Play the Tower game.')
    async def tower(self, ctx, amount: str):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        if amount.lower() == 'half':
            amount = user_data['balance'] / 2
        elif amount.lower() == 'all':
            amount = user_data['balance']
        elif amount.lower() == 'quarter':
            amount = user_data['balance'] / 4
        else:
            try:
                amount = float(amount)
            except ValueError:
                await ctx.send(f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", delete_after=5)
                return

        if amount <= 0:
            await ctx.send(f"🚫 {ctx.author.mention}, **Error**: You must bet a positive amount.", delete_after=5)
            return

        if user_data['balance'] < amount:
            await ctx.send(f"🚫 {ctx.author.mention}, **Error**: You do not have enough dollars to bet.", delete_after=5)
            return

        game = TowerGame(ctx, amount, self)
        embed = game.create_embed()
        await ctx.send(embed=embed, view=game)

    @tower.error
    async def tower_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", delete_after=5)

    @commands.command(name='slots', description='Play the slot machine.')
    async def slots(self, ctx, amount: str):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        if amount.lower() == 'half':
            amount = user_data['balance'] / 2
        elif amount.lower() == 'all':
            amount = user_data['balance']
        elif amount.lower() == 'quarter':
            amount = user_data['balance'] / 4
        else:
            try:
                amount = float(amount)
            except ValueError:
                await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", discord.Color.red(), delete_after=5)
                return

        if amount <= 0:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You must bet a positive amount.", discord.Color.red(), delete_after=5)
            return

        if user_data['balance'] < amount:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You do not have enough dollars to bet.", discord.Color.red(), delete_after=5)
            return

        symbols = ['🍒', '🍋', '🍊', '🍇', '🔔', '💎']
        result = [random.choice(symbols) for _ in range(3)]

        if result[0] == result[1] == result[2]:
            if result[0] == '💎':
                winnings = amount * 10
            elif result[0] == '🔔':
                winnings = amount * 5
            else:
                winnings = amount * 3
        elif result[0] == result[1] or result[1] == result[2]:
            winnings = amount * 1.5
        else:
            winnings = 0

        user_data['balance'] += winnings - amount
        await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

        result_str = ' '.join(result)
        if winnings > amount:
            color = discord.Color.green()
            title = f"You Won ${winnings - amount:,.2f}!"
        elif winnings == amount:
            color = discord.Color.yellow()
            title = "You Broke Even!"
        else:
            color = discord.Color.red()
            title = f"You Lost ${amount - winnings:,.2f}!"

        embed = discord.Embed(
            title=title,
            description=f"🎰 {result_str} 🎰\n\nYou bet **${amount:,.2f}** and won **${winnings:,.2f}**.\nIn total, you have **${user_data['balance']:,.2f}** left. 💵",
            color=color
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @slots.error
    async def slots_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", discord.Color.red(), delete_after=5)


    @commands.command(name='coinflip', aliases=['cf'], description='Flip a coin and gamble your money.')
    async def coinflip(self, ctx, amount: str):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        if amount.lower() == 'half':
            amount = user_data['balance'] / 2
        elif amount.lower() == 'all':
            amount = user_data['balance']
        elif amount.lower() == 'quarter':
            amount = user_data['balance'] / 4
        else:
            try:
                amount = float(amount)
            except ValueError:
                await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", discord.Color.red(), delete_after=5)
                return

        if amount <= 0:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You must gamble a positive amount.", discord.Color.red(), delete_after=5)
            return

        if user_data['balance'] < amount:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You do not have enough dollars to gamble.", discord.Color.red(), delete_after=5)
            return

        # Coin flip outcome
        outcome = random.choice(['Heads', 'Tails'])
        
        # Assume the user calls 'Heads' or 'Tails' as the guess. You could add that as an argument if you want.
        guess = random.choice(['Heads', 'Tails'])  # For example purposes; replace with actual user guess if available

        if guess == outcome:
            winnings = amount
            user_data['balance'] += winnings
            await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

            embed = discord.Embed(
                title=f"You Won ${winnings:,.2f}!",
                description=f"Flipped a coin and guessed **{guess}**.\nThe coin landed on **{outcome}**.\nYou bet **${amount:,.2f}** and won **${winnings:,.2f}**.\nIn total, you have **${user_data['balance']:,.2f}** left. 💵",
                color=discord.Color.green()
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
        else:
            user_data['balance'] -= amount
            await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

            embed = discord.Embed(
                title=f"You Lost ${amount:,.2f}!",
                description=f"Flipped a coin and guessed **{guess}**.\nThe coin landed on **{outcome}**.\nYou bet **${amount:,.2f}** and lost.\nIn total, you have **${user_data['balance']:,.2f}** left. 💵",
                color=discord.Color.red()
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)



    @commands.command(name='gamble', description='Gamble your money.')
    async def gamble(self, ctx, amount: str):
        user_id = ctx.author.id
        user_data = await self.get_user_data(user_id)

        if amount.lower() == 'half':
            amount = user_data['balance'] / 2
        elif amount.lower() == 'all':
            amount = user_data['balance']
        elif amount.lower() == 'quarter':
            amount = user_data['balance'] / 4
        else:
            try:
                amount = float(amount)
            except ValueError:
                await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", discord.Color.red(), delete_after=5)
                return

        if amount <= 0:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You must gamble a positive amount.", discord.Color.red(), delete_after=5)
            return

        if user_data['balance'] < amount:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You do not have enough dollars to gamble.", discord.Color.red(), delete_after=5)
            return

        dice_roll = random.randint(1, 100)
        if dice_roll < 50:
            user_data['balance'] -= amount
            await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

            embed = discord.Embed(
                title=f"You Lost ${amount:,.2f}!",
                description=f"Gambled **${amount:,.2f}**\ndollars out of **${user_data['balance'] + amount:,.2f}**.\nRolled a **{dice_roll}**/100. 🎲 Better luck next time. 📉\nIn total, you have **${user_data['balance']:,.2f}** left. 💵",
                color=discord.Color.red()
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
        elif dice_roll == 50:
            user_data['balance'] -= amount / 2
            await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

            embed = discord.Embed(
                title=f"You Lost ${amount / 2:,.2f}!",
                description=f"Gambled **${amount:,.2f}**\ndollars out of **${user_data['balance'] + amount:,.2f}**.\nRolled a **{dice_roll}**/100. 🎲 Couldve Been Worse. 🟰\nIn total, you have **${user_data['balance']:,.2f}** left. 💵",
                color=discord.Color.yellow()
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
        else:
            winnings = amount * (dice_roll / 100)
            user_data['balance'] += winnings
            await self.update_user_data(user_id, user_data['balance'], user_data['bank'])

            embed = discord.Embed(
                title=f"You Won ${winnings:,.2f}!",
                description=f"Gambled **${amount:,.2f}**\ndollars out of **${user_data['balance'] - winnings:,.2f}**.\nRolled a **{dice_roll}**/100. 🎲 Congratulations! 📈\nIn total, you have **${user_data['balance']:,.2f}** left. 💵",
                color=discord.Color.green()
            )
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.command(name='pay', description='Transfer money to another user.', aliases=['give'])
    async def pay(self, ctx, member: discord.Member, amount: float):
        if member == ctx.author:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You cannot pay yourself.", discord.Color.red(), delete_after=5)
            return

        if amount <= 0:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You must transfer a positive amount.", discord.Color.red(), delete_after=5)
            return

        user_id = ctx.author.id
        target_id = member.id

        user_data = await self.get_user_data(user_id)
        target_data = await self.get_user_data(target_id)

        # Add a small tolerance to account for floating-point precision errors
        tolerance = 1e-6
        if user_data['balance'] < amount + tolerance:
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: You do not have enough dollars to transfer.", discord.Color.red(), delete_after=5)
            return

        # Calculate the fee based on the amount
        if amount < 1000:
            fee_percentage = 0
        elif amount < 5000:
            fee_percentage = 0.05  # 5% fee
        elif amount < 10000:
            fee_percentage = 0.10  # 10% fee
        else:
            fee_percentage = 0.15  # 15% fee

        fee_amount = amount * fee_percentage
        amount_after_fee = amount - fee_amount

        user_data['balance'] -= amount
        target_data['balance'] += amount_after_fee

        await self.update_user_data(user_id, user_data['balance'], user_data['bank'])
        await self.update_user_data(target_id, target_data['balance'], target_data['bank'])

        await self.send_embed(ctx, f"🏦 {ctx.author.mention}, **Transferred**: ${amount_after_fee:,.2f} to {member.mention} with a **{fee_percentage * 100}%** fee.", discord.Color.green())


    @commands.command(name='leaderboard', description='Display the top users by balance.', aliases=['leader', 'lb','gml'])
    async def leaderboard(self, ctx):
        async with aiosqlite.connect(self.db_name) as conn:
            async with conn.execute('SELECT user_id, balance, bank FROM user_data ORDER BY (balance + bank) DESC LIMIT 100') as cursor:
                results = await cursor.fetchall()

        if not results:
            await ctx.send(f"{ctx.author.mention}, No users found.", delete_after=5)
            return

        pages = [results[i:i + 10] for i in range(0, len(results), 10)]
        view = LeaderboardView(self.bot, pages)
        embed = view.create_embed(pages[0], 0)
        view.message = await ctx.send(embed=embed, view=view)

    @balance.error
    async def balance_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid user.", discord.Color.red(), delete_after=5)

    @deposit.error
    async def deposit_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", discord.Color.red(), delete_after=5)

    @withdraw.error
    async def withdraw_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid amount.", discord.Color.red(), delete_after=5)

    @beg.error
    async def beg_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await self.send_embed(ctx, f"🕐 {ctx.author.mention}, **Error**: You need to wait {int(error.retry_after)} seconds before you can beg again.", discord.Color.yellow(), delete_after=5)

    @search.error
    async def search_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await self.send_embed(ctx, f"🕐 {ctx.author.mention}, **Error**: You need to wait {int(error.retry_after)} seconds before you can search again.", discord.Color.yellow(), delete_after=5)

    @daily.error
    async def daily_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await self.send_embed(ctx, f"🕐 {ctx.author.mention}, **Error**: You need to wait {int(error.retry_after)} seconds before you can claim your daily reward again.", discord.Color.yellow(), delete_after=5)

    @weekly.error
    async def weekly_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await self.send_embed(ctx, f"🕐 {ctx.author.mention}, **Error**: You need to wait {int(error.retry_after)} seconds before you can claim your weekly reward again.", discord.Color.yellow(), delete_after=5)

    @monthly.error
    async def monthly_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await self.send_embed(ctx, f"🕐 {ctx.author.mention}, **Error**: You need to wait {int(error.retry_after)} seconds before you can claim your monthly reward again.", discord.Color.yellow(), delete_after=5)

    @pay.error
    async def pay_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Missing required arguments.", discord.Color.red(), delete_after=5)
        elif isinstance(error, commands.BadArgument):
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: Invalid user or amount.", discord.Color.red(), delete_after=5)

    @leaderboard.error
    async def leaderboard_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await self.send_embed(ctx, f"🚫 {ctx.author.mention}, **Error**: An error occurred while fetching the leaderboard.", discord.Color.red(), delete_after=5)

class LeaderboardView(View):
    def __init__(self, bot, pages):
        super().__init__(timeout=360)
        self.bot = bot
        self.pages = pages
        self.current_page = 0
        self.message = None
        self.update_button_states()

    def update_button_states(self):
        # Disable buttons if there is only one page
        if len(self.pages) <= 1:
            self.disable_all_buttons()
        else:
            # Manage button states based on current page
            self.children[0].disabled = self.current_page == 0  # Previous button
            self.children[1].disabled = self.current_page == len(self.pages) - 1  # Next button

    def disable_all_buttons(self):
        for child in self.children:
            child.disabled = True

    def create_embed(self, page, page_num):
        def format_position(i, page_num):
            if page_num == 0:
                if i == 0:
                    return "👑"
                elif i == 1:
                    return "🥈"
                elif i == 2:
                    return "🥉"
            return f"`{i + 1 + page_num * 10}.`"

        leaderboard_text = "\n".join([
            f"{format_position(i, page_num)} **{self.bot.get_user(user_id).name if self.bot.get_user(user_id) else 'Unknown User'}** - ${net_worth:,.2f}"
            for i, (user_id, balance, bank) in enumerate(page)
            if (net_worth := balance + bank)
        ])
        embed = discord.Embed(title="Global Money Leaderboard", description=leaderboard_text, color=discord.Color.blue())
        embed.set_footer(text=f"Page {page_num + 1}/{len(self.pages)}")
        return embed

    async def update_embed(self, interaction: discord.Interaction):
        embed = self.create_embed(self.pages[self.current_page], self.current_page)
        self.update_button_states()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        else:
            self.current_page = len(self.pages) - 1
        await self.update_embed(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
        else:
            self.current_page = 0
        await self.update_embed(interaction)

    @discord.ui.button(label="Go to Page", style=discord.ButtonStyle.secondary)
    async def go_to_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PageModal(self))

    async def on_timeout(self):
        self.disable_all_buttons()
        if self.message:
            await self.message.edit(view=self)

class PageModal(Modal, title='Go to Page'):
    page_number = TextInput(label='Page Number', placeholder='Enter a page number...')

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_number.value) - 1
            if 0 <= page < len(self.view.pages):
                self.view.current_page = page
                await self.view.update_embed(interaction)
            else:
                await interaction.response.send_message(f"Invalid page number. Please enter a number between 1 and {len(self.view.pages)}.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Economy(bot))