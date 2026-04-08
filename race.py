import random
import math
import uuid
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List
from db import delete_racer_record, get_user_balance, set_user_balance, load_racer_records, upsert_racer_record, log_race_result


TRACK_LENGTH = 25
FINISH_STATE = TRACK_LENGTH - 1
MAX_TOTAL_STATS = 12
MAX_SINGLE_STAT = 5
UPGRADABLE_STATS = {"speed", "stamina", "charisma", "adrenaline"}
JOIN_RACE_COST = 25
RACER_COST_PER_OWNED = 100


@dataclass
class Racer:
    SPEED_REDUCTION_RATE = 2
    STAMINA_REDUCTION_PENALTY = 0.1
    ADRENALINE_BOOST_RATE = 25

    owner_id: int
    name: str
    racer_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    position: int = 0
    finished: bool = False
    stamina: float = 1
    speed: float = 1
    charisma: float = 1
    adrenaline: float = 1
    jump_chance: float = 0.0
    turns_taken: int = 0
    last_move: int = 0
    last_adrenaline_boost: bool = False
    in_race: bool = False
    creation_cost: int = 0

    def __post_init__(self):
        self._validate_stats()
        self.jump_chance = self.jump_rate()

    def _validate_stats(self):
        values = [self.speed, self.stamina, self.charisma, self.adrenaline]
        if not all(isinstance(value, int) for value in values):
            raise ValueError("All racer stats must be integers.")
        if not all(value >= 1 for value in values):
            raise ValueError("All racer stats must be at least 1.")
        if not all(value <= MAX_SINGLE_STAT for value in values):
            raise ValueError("Each racer stat must be 5 or less.")
        if sum(values) > MAX_TOTAL_STATS:
            raise ValueError("The sum of speed, stamina, charisma, and adrenaline must be at most 15.")

    def stats_total(self):
        return self.speed + self.stamina + self.charisma + self.adrenaline

    def upgrade_stat(self, stat_name: str, amount: int = 1):
        if stat_name not in UPGRADABLE_STATS:
            raise ValueError("Invalid stat. Use speed, stamina, charisma, or adrenaline.")
        if not isinstance(amount, int) or amount < 1:
            raise ValueError("Upgrade amount must be an integer greater than 0.")
        if self.stats_total() + amount > MAX_TOTAL_STATS:
            raise ValueError("Stat upgrade would exceed max total stats (15).")
        if getattr(self, stat_name) + amount > MAX_SINGLE_STAT:
            raise ValueError("Each stat is capped at 5.")

        setattr(self, stat_name, getattr(self, stat_name) + amount)
        self.jump_chance = self.jump_rate()

    def jump_rate(self):
        return 1 - math.exp(-self.speed / self.SPEED_REDUCTION_RATE)

    def stamina_penalty(self):
        return self.jump_chance - (self.jump_chance * self.STAMINA_REDUCTION_PENALTY / self.stamina)

    def adrenaline_boost(self):
        return 1 - math.exp(-self.adrenaline / self.ADRENALINE_BOOST_RATE)

    def chance_to_jump(self):
        adrenaline_roll = random.random()
        self.last_adrenaline_boost = False
        self.jump_chance = self.stamina_penalty()
        if adrenaline_roll < self.adrenaline_boost():
            self.jump_chance *= 1.2
            self.last_adrenaline_boost = True
        return min(self.jump_chance, 1.0)

    def advance(self):
        if self.finished:
            self.last_move = 0
            self.last_adrenaline_boost = False
            return 0

        self.jump_chance = self.chance_to_jump()
        if self.jump_chance < 0.01:
            self.last_move = 0
            return 0

        move = 0
        if self.position < FINISH_STATE and random.random() < self.jump_chance:
            self.position += 1
            move += 1

        self.turns_taken += 1
        self.last_move = move

        if self.position >= FINISH_STATE:
            self.position = FINISH_STATE
            self.finished = True

        return move


@dataclass
class Race:
    guild_id: int
    racers: List[Racer] = field(default_factory=list)
    turns: int = 0
    primary_by_owner: Dict[int, str] = field(default_factory=dict)
    result_logged: bool = False
    payouts_processed: bool = False
    bets_by_user: Dict[int, Dict[str, object]] = field(default_factory=dict)
    pending_finish_response: str = ""
    payout_summary_lines: List[str] = field(default_factory=list)

    def add_racer(
        self,
        owner_id: int,
        name: str,
        speed: int = 1,
        stamina: int = 1,
        charisma: int = 1,
        adrenaline: int = 1,
        creation_cost: int = 0,
    ) -> Racer:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Racer name cannot be empty.")

        if any(racer.name.lower() == clean_name.lower() for racer in self.racers):
            raise ValueError("A racer with that name already exists in this race.")

        racer = Racer(
            owner_id=owner_id,
            name=clean_name,
            speed=speed,
            stamina=stamina,
            charisma=charisma,
            adrenaline=adrenaline,
            creation_cost=creation_cost,
        )
        self.racers.append(racer)
        if owner_id not in self.primary_by_owner:
            self.primary_by_owner[owner_id] = racer.racer_id
        return racer

    def find_racer(self, owner_id: int, racer_name: str) -> Racer:
        clean_name = racer_name.strip().lower()
        for racer in self.racers:
            if racer.owner_id == owner_id and racer.name.lower() == clean_name:
                return racer
        raise ValueError("You do not own a racer with that name.")

    def joined_racers(self) -> List[Racer]:
        return [racer for racer in self.racers if racer.in_race]

    def set_primary_racer(self, owner_id: int, racer_name: str) -> Racer:
        racer = self.find_racer(owner_id, racer_name)
        self.primary_by_owner[owner_id] = racer.racer_id
        return racer

    def get_primary_racer(self, owner_id: int) -> Racer:
        racer_id = self.primary_by_owner.get(owner_id)
        if racer_id is None:
            raise ValueError("You do not have a primary racer set.")

        for racer in self.racers:
            if racer.racer_id == racer_id and racer.owner_id == owner_id:
                return racer

        raise ValueError("Your primary racer was not found.")

    def join_primary_racer(self, owner_id: int) -> Racer:
        racer = self.get_primary_racer(owner_id)
        if racer.in_race:
            raise ValueError("Your primary racer is already in this race.")
        racer.in_race = True
        return racer

    def place_bet(self, user_id: int, racer_index: int, wager: int):
        if self.is_over():
            raise ValueError("Race is already finished. Betting is closed.")

        active = self.joined_racers()
        if not active:
            raise ValueError("No racers have joined this race yet.")

        if any(r.owner_id == user_id for r in active):
            raise ValueError("Users with a racer in this race cannot place bets.")

        if user_id in self.bets_by_user:
            raise ValueError("You have already placed a bet for this race.")

        if not isinstance(racer_index, int) or racer_index < 1 or racer_index > len(active):
            raise ValueError("Invalid racer index.")
        if not isinstance(wager, int) or wager < 1:
            raise ValueError("Wager must be a positive integer.")

        balance = get_user_balance(user_id)
        if wager > balance:
            raise ValueError(f"Insufficient balance. You have {balance}.")

        target = active[racer_index - 1]
        set_user_balance(user_id, balance - wager)
        self.bets_by_user[user_id] = {
            'racer_id': target.racer_id,
            'racer_name': target.name,
            'wager': wager,
        }

    def settle_payouts(self):
        if self.payouts_processed:
            return
        if not self.is_over():
            return

        active_racers = self.joined_racers()
        standings = self.standings()
        rank_by_name = {row['name'].lower(): row['rank'] for row in standings}
        finish_multiplier = {1: 1.8, 2: 1.5, 3: 1.3}
        bet_multiplier = {1: 1.0, 2: 0.5, 3: 0.1}
        owner_payout_lines = []
        bettor_payout_lines = []
        solo_race = len(active_racers) < 2
        one_v_one = len(active_racers) == 2

        if one_v_one:
            finish_multiplier = {1: 1.5, 2: 0.0}
            bet_multiplier = {1: 1.5, 2: 0.0}

        # Pay racer owners based on placement and charisma.
        for racer in active_racers:
            rank = rank_by_name.get(racer.name.lower())
            placement_mult = finish_multiplier.get(rank, 0.0) if isinstance(rank, int) else 0.0
            if solo_race:
                placement_mult = 0.0
            balance = get_user_balance(racer.owner_id)
            reward = int(balance * placement_mult * racer.charisma) if placement_mult > 0 else 0
            new_balance = balance
            if reward > 0:
                new_balance = balance + reward
                set_user_balance(racer.owner_id, new_balance)

            owner_payout_lines.append(
                f"{racer.name} (<@{racer.owner_id}>): +{reward} -> balance {new_balance}"
            )

        # Pay bettors based on selected racer placement and charisma.
        racer_by_id = {r.racer_id: r for r in active_racers}
        for bettor_id, bet in self.bets_by_user.items():
            racer = racer_by_id.get(str(bet['racer_id']))
            wager = int(bet['wager'])
            if racer is None:
                balance = get_user_balance(bettor_id)
                bettor_payout_lines.append(
                    f"<@{bettor_id}> (unknown racer, wager {wager}): +0 -> balance {balance}"
                )
                continue

            rank = rank_by_name.get(racer.name.lower())
            placement_mult = bet_multiplier.get(rank, 0.0) if isinstance(rank, int) else 0.0
            if solo_race:
                placement_mult = 0.0
            reward = int(racer.charisma * wager * placement_mult)
            balance = get_user_balance(bettor_id)
            new_balance = balance
            if reward > 0:
                new_balance = balance + reward
                set_user_balance(bettor_id, new_balance)

            bettor_payout_lines.append(
                f"<@{bettor_id}> on {racer.name} (wager {wager}): +{reward} -> balance {new_balance}"
            )

        self.payout_summary_lines = ["Payout Summary", "Players"]
        if solo_race:
            self.payout_summary_lines.append("Solo race detected: no payouts awarded.")
        elif one_v_one:
            self.payout_summary_lines.append("1v1 rules: winner gets 1.5x, loser gets 0.")
        if owner_payout_lines:
            self.payout_summary_lines.extend(owner_payout_lines)
        else:
            self.payout_summary_lines.append("No player payouts.")

        self.payout_summary_lines.append("Bettors")
        if bettor_payout_lines:
            self.payout_summary_lines.extend(bettor_payout_lines)
        else:
            self.payout_summary_lines.append("No bets placed.")

        self.payouts_processed = True

    def reset_for_next_race(self):
        for racer in self.joined_racers():
            racer.position = 0
            racer.finished = False
            racer.jump_chance = racer.jump_rate()
            racer.turns_taken = 0
            racer.last_move = 0
            racer.last_adrenaline_boost = False
            racer.in_race = False

        self.turns = 0
        self.result_logged = False
        self.payouts_processed = False
        self.bets_by_user = {}
        self.payout_summary_lines = []

    def advance(self):
        active = self.joined_racers()
        if not active:
            return self

        if self.is_over():
            return self

        self.turns += 1
        for racer in active:
            racer.advance()
        return self

    def standings(self):
        active = self.joined_racers()
        finishers = [r for r in active if r.finished]
        dnfs = [r for r in active if not r.finished and r.jump_chance < 0.05]

        finishers.sort(key=lambda r: (r.turns_taken, -r.position, r.name.lower()))
        dnfs.sort(key=lambda r: (-r.position, r.turns_taken, r.name.lower()))

        rows = []
        for idx, racer in enumerate(finishers, start=1):
            rows.append({
                'rank': idx,
                'name': racer.name,
                'owner_id': racer.owner_id,
                'status': 'FINISHED',
                'position': racer.position,
                'turns_taken': racer.turns_taken,
            })
        for racer in dnfs:
            rows.append({
                'rank': 'DNF',
                'name': racer.name,
                'owner_id': racer.owner_id,
                'status': 'DNF',
                'position': racer.position,
                'turns_taken': racer.turns_taken,
            })
        return rows

    def finish_response(self):
        rows = self.standings()
        if not rows:
            return 'No racers joined this race.'

        lines = [f'Race finished in {self.turns} turns.']
        for row in rows:
            if row['rank'] == 'DNF':
                lines.append(f"DNF - {row['name']} (<@{row['owner_id']}>) - {row['position']}/24")
            else:
                lines.append(f"#{row['rank']} - {row['name']} (<@{row['owner_id']}>)")

        if self.payout_summary_lines:
            lines.append("")
            lines.extend(self.payout_summary_lines)
        return "\n".join(lines)

    def all_finished(self) -> bool:
        active = self.joined_racers()
        return bool(active) and all(racer.finished for racer in active)

    def all_stalled(self) -> bool:
        active = self.joined_racers()
        return bool(active) and all(racer.finished or racer.jump_chance < 0.05 for racer in active)

    def is_over(self) -> bool:
        return self.all_finished() or self.all_stalled()

    def _track_for_racer(self, racer: Racer) -> str:
        cells = [" - "] * TRACK_LENGTH
        if racer.name.startswith("<:") or racer.name.startswith("<a:"):
            marker = racer.name
        else:
            first_char = racer.name[:1]
            if not first_char:
                marker = "R"
            elif first_char == ":":
                marker = "R"
            else:
                marker = first_char.upper() if first_char.isalnum() else first_char
        cells[racer.position] = marker
        return "|" + "".join(cells) + "|"

    def summary_lines(self) -> List[str]:
        lines = []
        for index, racer in enumerate(self.joined_racers(), start=1):
            owner = f"<@{racer.owner_id}>"
            status = "finished" if racer.finished else f"% to move {racer.jump_chance:.2f}"
            boost_text = " - ADRENALINE BOOST" if racer.last_adrenaline_boost else ""
            lines.append(
                f"{index}. {racer.name} - {owner} - {status}{boost_text}"
            )
        return lines

    def track_lines(self) -> List[str]:
        return [self._track_for_racer(racer) for racer in self.joined_racers()]


_races: Dict[int, Race] = {}


def _racer_creation_cost(race: Race, owner_id: int) -> int:
    existing_count = sum(1 for racer in race.racers if racer.owner_id == owner_id)
    return existing_count * RACER_COST_PER_OWNED


def _serialize_racer(race: Race, racer: Racer):
    return {
        'racer_id': racer.racer_id,
        'owner_id': str(racer.owner_id),
        'name': racer.name,
        'position': racer.position,
        'finished': racer.finished,
        'stamina': racer.stamina,
        'speed': racer.speed,
        'charisma': racer.charisma,
        'adrenaline': racer.adrenaline,
        'jump_chance': racer.jump_chance,
        'turns_taken': racer.turns_taken,
        'last_move': racer.last_move,
        'last_adrenaline_boost': racer.last_adrenaline_boost,
        'in_race': racer.in_race,
        'creation_cost': racer.creation_cost,
        'is_primary': race.primary_by_owner.get(racer.owner_id) == racer.racer_id,
        'result_logged': race.result_logged,
        'payouts_processed': race.payouts_processed,
    }


def _persist_racer(guild_id: int, race: Race, racer: Racer):
    upsert_racer_record(guild_id, _serialize_racer(race, racer))


def _persist_racers(guild_id: int, race: Race, racers: List[Racer]):
    for racer in racers:
        _persist_racer(guild_id, race, racer)


def _load_race_from_db(guild_id: int) -> Race:
    race = Race(guild_id=guild_id)
    records = load_racer_records(guild_id)

    for record in records:
        owner_id = int(record.get('owner_id'))
        racer = Racer(
            owner_id=owner_id,
            name=str(record.get('name', 'Unknown')),
            racer_id=str(record.get('racer_id', uuid.uuid4().hex[:8])),
            position=int(record.get('position', 0)),
            finished=bool(record.get('finished', False)),
            stamina=int(record.get('stamina', 1)),
            speed=int(record.get('speed', 1)),
            charisma=int(record.get('charisma', 1)),
            adrenaline=int(record.get('adrenaline', 1)),
            turns_taken=int(record.get('turns_taken', 0)),
            last_move=int(record.get('last_move', 0)),
            last_adrenaline_boost=bool(record.get('last_adrenaline_boost', False)),
            in_race=bool(record.get('in_race', False)),
            creation_cost=int(record.get('creation_cost', 0)),
        )
        racer.jump_chance = float(record.get('jump_chance', racer.jump_chance))
        race.racers.append(racer)
        if bool(record.get('result_logged', False)):
            race.result_logged = True
        if bool(record.get('payouts_processed', False)):
            race.payouts_processed = True
        if bool(record.get('is_primary', False)):
            race.primary_by_owner[owner_id] = racer.racer_id

    race.turns = max((racer.turns_taken for racer in race.racers), default=0)
    return race


def get_race(guild_id: int) -> Race:
    race = _races.get(guild_id)
    if race is None:
        race = _load_race_from_db(guild_id)
        _races[guild_id] = race
    return race


def create_racer(guild_id: int, owner_id: int, name: str) -> Racer:
    race = get_race(guild_id)
    creation_cost = _racer_creation_cost(race, owner_id)
    balance = get_user_balance(owner_id)
    if creation_cost > balance:
        raise ValueError(f"Creating a new racer costs {creation_cost}. You have {balance}.")

    racer = race.add_racer(owner_id=owner_id, name=name, creation_cost=creation_cost)
    if creation_cost > 0:
        set_user_balance(owner_id, balance - creation_cost)
    _persist_racer(guild_id, race, racer)
    return racer


def create_racer_with_stats(
    guild_id: int,
    owner_id: int,
    name: str,
    speed: int,
    stamina: int,
    charisma: int,
    adrenaline: int,
) -> Racer:
    race = get_race(guild_id)
    creation_cost = _racer_creation_cost(race, owner_id)
    balance = get_user_balance(owner_id)
    if creation_cost > balance:
        raise ValueError(f"Creating a new racer costs {creation_cost}. You have {balance}.")

    racer = race.add_racer(
        owner_id=owner_id,
        name=name,
        speed=speed,
        stamina=stamina,
        charisma=charisma,
        adrenaline=adrenaline,
        creation_cost=creation_cost,
    )
    if creation_cost > 0:
        set_user_balance(owner_id, balance - creation_cost)
    _persist_racer(guild_id, race, racer)
    return racer


def increase_racer_stat(guild_id: int, owner_id: int, racer_name: str, stat_name: str, amount: int = 1) -> Racer:
    race = get_race(guild_id)
    racer = race.find_racer(owner_id=owner_id, racer_name=racer_name)
    racer.upgrade_stat(stat_name.lower().strip(), amount)
    _persist_racer(guild_id, race, racer)
    return racer


def set_primary_racer(guild_id: int, owner_id: int, racer_name: str) -> Racer:
    race = get_race(guild_id)
    racer = race.set_primary_racer(owner_id=owner_id, racer_name=racer_name)
    owner_racers = [r for r in race.racers if r.owner_id == owner_id]
    _persist_racers(guild_id, race, owner_racers)
    return racer


def remove_racer_by_index(guild_id: int, owner_id: int, racer_index: int):
    race = get_race(guild_id)
    owner_racers = [r for r in race.racers if r.owner_id == owner_id]
    if not isinstance(racer_index, int) or racer_index < 1 or racer_index > len(owner_racers):
        raise ValueError("Invalid racer index.")

    racer = owner_racers[racer_index - 1]
    if racer.in_race:
        raise ValueError("You cannot remove a racer that is currently in a race.")

    race.racers.remove(racer)

    if race.primary_by_owner.get(owner_id) == racer.racer_id:
        remaining_owner_racers = [r for r in race.racers if r.owner_id == owner_id]
        if remaining_owner_racers:
            race.primary_by_owner[owner_id] = remaining_owner_racers[0].racer_id
        else:
            race.primary_by_owner.pop(owner_id, None)

    refund = int(max(0, racer.creation_cost) * 0.5)
    if refund > 0:
        balance = get_user_balance(owner_id)
        set_user_balance(owner_id, balance + refund)

    delete_racer_record(guild_id, racer.racer_id)
    remaining_owner_racers = [r for r in race.racers if r.owner_id == owner_id]
    _persist_racers(guild_id, race, remaining_owner_racers)
    return racer, refund


def join_primary_racer(guild_id: int, owner_id: int) -> Racer:
    race = get_race(guild_id)
    balance = get_user_balance(owner_id)
    if JOIN_RACE_COST > balance:
        raise ValueError(f"Joining the race costs {JOIN_RACE_COST}. You have {balance}.")

    racer = race.join_primary_racer(owner_id=owner_id)
    set_user_balance(owner_id, balance - JOIN_RACE_COST)
    _persist_racer(guild_id, race, racer)
    return racer


def is_primary_racer(guild_id: int, owner_id: int, racer_name: str) -> bool:
    race = get_race(guild_id)
    try:
        primary = race.get_primary_racer(owner_id)
    except ValueError:
        return False
    return primary.name.lower() == racer_name.strip().lower()


def advance_race(guild_id: int) -> Race:
    race = get_race(guild_id)
    race.advance()

    if race.is_over() and not race.payouts_processed:
        race.settle_payouts()

    if race.is_over() and not race.result_logged:
        finish_text = race.finish_response()
        standings = race.standings()
        signature_source = "|".join(
            f"{row['name']}:{row['rank']}:{row['position']}:{row['turns_taken']}" for row in standings
        )
        signature = hashlib.sha256(f"{guild_id}:{race.turns}:{signature_source}".encode("utf-8")).hexdigest()
        log_race_result(guild_id, signature, race.turns, standings)
        race.result_logged = True
        race.pending_finish_response = finish_text

    _persist_racers(guild_id, race, race.racers)
    return race


def start_new_race(guild_id: int) -> Race:
    race = get_race(guild_id)
    if not race.joined_racers():
        raise ValueError("No racers have joined this race yet.")
    if not race.is_over():
        raise ValueError("The current race is still in progress.")

    race.reset_for_next_race()
    race.pending_finish_response = ""
    _persist_racers(guild_id, race, race.racers)
    return race


def race_is_over(guild_id: int) -> bool:
    return get_race(guild_id).is_over()


def get_race_message(guild_id: int) -> str:
    race = get_race(guild_id)
    if not race.racers:
        return "No racers have been created yet. Use racers -> Create Racer to add one."

    if not race.joined_racers():
        return "No racers have joined this race yet. Set a primary racer and press Join Race."

    if race.all_finished():
        return race.finish_response()

    if race.all_stalled():
        return race.finish_response()

    return "Race in progress."


def get_race_finish_response(guild_id: int) -> str:
    return get_race(guild_id).finish_response()


def consume_pending_finish_response(guild_id: int) -> str:
    race = get_race(guild_id)
    text = race.pending_finish_response
    race.pending_finish_response = ""
    return text


def place_race_bet(guild_id: int, user_id: int, racer_index: int, wager: int):
    race = get_race(guild_id)
    race.place_bet(user_id=user_id, racer_index=racer_index, wager=wager)
    return race