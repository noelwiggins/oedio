"""ANTHROPOGENESIS — the origin and development of humanity.

A continent under shifting ice ages, and small bands of people living on it. Each band forages where the land is
kind and moves when it is not. What makes them human here is culture: a band invents (a better tool, the keeping
of fire, words, images) with odds that rise with its size and its talk; it can also forget, and a small band
loses skills it can no longer keep alive. Bands that meet and trust each other share what they know; bands that
don't, fight. A band that grows big splits, and the daughter band carries its culture away with it.

So knowledge ratchets upward where people are many and connected, and slips back where they are few and alone.
Cold drives bands south unless they keep fire; warmth opens the north. Nothing is scripted: when fire, language
and art appear, and where, is decided by population, contact and climate.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

W, H = 1200.0, 640.0
GX, GY = 60, 32
CAP = 200
CAP_S = 40                                   # settlements
# the trades, in the order a growing settlement can support them: (name, people needed, what else it needs)
ROLES = ["toolmakers", "builders", "potters", "traders", "priests", "smiths", "scribes"]
ROLE_POP = [60, 90, 150, 220, 320, 500, 800]
TIERS = ["camp", "hamlet", "village", "walled village", "town", "city"]


class Anthropogenesis(World):
    SLUG = "anthropogenesis"
    TITLE = "Anthropogenesis"
    DEFINITION = "The origin and development of humanity"
    TAGLINE = "Bands of people under shifting ice ages: knowledge ratchets up where they are many and connected."
    TPS = 10.0
    STATS_EVERY = 200
    EPOCH = 4000
    LIGHT_CYCLE = 2000
    ABOUT = [
        "A continent under shifting ice ages, and small bands of people living on it. Each band forages where the land is kind and moves when it is not; the ice in the north comes and goes.",
        "What makes them human here is culture. A band invents (a better tool, the keeping of fire, words, images) with odds that rise with its size and its talk. It can also forget: a small band loses skills it can no longer keep alive.",
        "Bands that meet and trust each other share what they know; bands that don't, fight. A band that grows big splits, and the daughter carries its culture away. Fires show at night; painted bands wear a red mark.",
        "Knowledge ratchets up where people are many and connected and slips back where they are few and alone. When fire, language and art appear, and where, is decided by numbers, contact and climate.",
        "A band that knows enough, on kind land, may learn to farm, and stay. A settlement's surplus frees people from finding food, and the bigger it is, the more trades it can keep: toolmakers, then builders, potters, traders, priests and artists, smiths, and at last scribes. Nobody plans this; it is how many hands there are and how much food is spare.",
        "Builders raise the place from a hamlet of round huts to a village with houses, fields and a granary, a walled village with workshops, a town with stone walls, a market and a temple, and a city with a citadel, a forge and a monument. Traders join towns by roads, and knowledge travels along them.",
        "The little figures in a settlement are its people at their work, coloured by trade: green farmers in the fields, rust toolmakers, ochre builders at the scaffolds, blue potters at the kilns, gold traders at the market, violet priests at the temple, red smiths at the forge, ink scribes at the citadel. A settlement that loses its people loses its trades first, and its walls fall into ruin.",
    ]
    STAT_LABELS = [("people", "People"), ("bands", "Bands"), ("settlements", "Settlements"), ("townsfolk", "People in settlements"),
                   ("trades", "Most trades in one place"), ("tier_max", "Grandest settlement (0 camp … 5 city)"), ("biggest", "Biggest settlement"), ("tools_max", "Best tools (level)"), ("tools_mean", "Tools, average"),
                   ("fire", "Bands keeping fire (%)"), ("language", "Language, average (0-1)"), ("art", "Bands making art (%)"),
                   ("range", "Land settled (%)"), ("ice", "Land under ice (%)")]
    SERIES = [[("people", "People", "#e5602a")], [("tools_mean", "Tools, average", "#f2b33d"), ("language_x10", "Language ×10", "#c9b6ff")],
              [("fire", "Fire %", "#e58bb0"), ("art", "Art %", "#a8c94a"), ("ice", "Ice %", "#8fd3c8")],
              [("townsfolk", "In settlements", "#c0392b"), ("trades_x100", "Trades ×100", "#f2b33d")]]
    DIALS = [D("climate", "Climate", "snow", "#8fd3c8", "Cold", "Warm",
               "Pushes the world toward an ice age or a warm spell. Cold squeezes bands south and makes fire precious; warmth opens the north."),
             D("bounty", "Bounty", "leaf", "#a8c94a", "Lean", "Plentiful",
               "How much the land yields. Plenty swells bands, and big bands invent; lean years break bands up and skills are lost.")]
    LYSIS_NAME = "Anthropophthora"
    LYSIS_ABOUT = [
        "Anthropophthora: the undoing of what people made. Here it is not extinction but collapse. A band that dwindles away, starves in the cold or is broken by a quarrel leaves its camp behind: hearths, worked stone, painted walls.",
        "The ruins keep what the band knew. The ice may cover them for an age and then give them back. A later band that camps on a ruin of people who knew more learns from what it finds, and a lost skill comes back into the world.",
        "So knowledge is not only passed from the living: it is buried and rediscovered, and a collapse can seed a renaissance.",
        "On the underside living bands are dim embers, ruins glow amber by how much they knew, ruins under the ice glow blue-white, and a rediscovery flares in bone.",
    ]
    JOURNAL_HINT = ("These are bands of early humans and, later, their farms and settlements: speak of bands, people, tools, fire, "
                    "language, art, ice, migration, meetings and quarrels, farming, hamlets, villages, towns, trades and roads. "
                    "Do not name real places or real archaeological cultures.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        yy, xx = np.mgrid[0:GY, 0:GX].astype(np.float32)
        base = 0.55 + 0.35 * (yy / GY)                       # kinder toward the south
        for _ in range(10):
            cx, cy, r, a = rng.uniform(0, GX), rng.uniform(0, GY), rng.uniform(4, 12), rng.normal(0, 0.35)
            base += a * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r))
        self.lat = (yy / GY).astype(np.float32)               # 0 north, 1 south
        self.base = np.clip(base, 0.05, 1.3).astype(np.float32)
        self.alive = np.zeros(CAP, bool)
        self.x, self.y = np.zeros(CAP, np.float32), np.zeros(CAP, np.float32)
        self.size = np.zeros(CAP, np.float32)
        self.tools, self.lang, self.art = (np.zeros(CAP, np.float32) for _ in range(3))
        self.fire = np.zeros(CAP, bool)
        self.coop = np.zeros(CAP, np.float32)
        self.lin = np.zeros(CAP, np.int64)
        self.next_lin = 1
        self._lysis_init()
        self._civ_init()
        for _ in range(8):
            self._band(rng.uniform(400, 800), rng.uniform(450, 600), 20, 0, False, 0, 0, rng.uniform(0.3, 0.7), None)

    # ── settlements and the division of labour ────────────────────────────
    def _civ_init(self):
        if hasattr(self, "s_alive"):
            return
        self.farm = np.zeros(CAP, bool)                 # bands that have learned to farm
        self.s_alive = np.zeros(CAP_S, bool)
        self.s_id = np.zeros(CAP_S, np.int64)
        self.s_x, self.s_y = np.zeros(CAP_S, np.float32), np.zeros(CAP_S, np.float32)
        self.s_pop, self.s_built = np.zeros(CAP_S, np.float32), np.zeros(CAP_S, np.float32)
        self.s_tools, self.s_lang, self.s_art = (np.zeros(CAP_S, np.float32) for _ in range(3))
        self.s_coop = np.zeros(CAP_S, np.float32)
        self.s_lin = np.zeros(CAP_S, np.int64)
        self.s_tier = np.zeros(CAP_S, np.int8)
        self.s_roles = np.zeros((CAP_S, len(ROLES)), np.float32)    # share of the people in each trade
        self.s_found = np.zeros(CAP_S, np.int64)
        self.s_links = []
        self.next_sid = 1

    def _unlocked(self, k, links):
        """Which trades settlement k can keep: enough people, and what each trade needs besides."""
        pop = float(self.s_pop[k])
        ok = [pop >= ROLE_POP[0], pop >= ROLE_POP[1], pop >= ROLE_POP[2],
              pop >= ROLE_POP[3] and links > 0,
              pop >= ROLE_POP[4] and self.s_art[k] >= 1,
              pop >= ROLE_POP[5] and self.s_tools[k] >= 40,
              pop >= ROLE_POP[6] and self.s_lang[k] >= 0.8]
        return np.array(ok)

    def _found(self, i):
        free = np.flatnonzero(~self.s_alive)
        if not len(free):
            return None
        k = int(free[0])
        self.s_alive[k] = True
        self.s_id[k] = self.next_sid; self.next_sid += 1
        self.s_x[k], self.s_y[k] = self.x[i], self.y[i]
        self.s_pop[k] = self.size[i]; self.s_built[k] = 0
        self.s_tools[k], self.s_lang[k], self.s_art[k], self.s_coop[k] = self.tools[i], self.lang[i], self.art[i], self.coop[i]
        self.s_lin[k] = self.lin[i]; self.s_tier[k] = 1; self.s_roles[k] = 0; self.s_found[k] = self.tick
        self.alive[i] = False
        self.milestone("hamlet", "A farming band has stopped wandering and built a hamlet: round huts around a shared hearth.")
        return k

    def _civ(self, prod, ice):
        """Every tenth tick: farming bands settle; settlements grow, take up trades, build, trade, decline."""
        rng = self.rng
        self._civ_init()
        A = np.flatnonzero(self.alive)
        S = np.flatnonzero(self.s_alive)
        # farming bands settle: join a settlement nearby, or found one where there is room
        for i in A[self.farm[A]]:
            if not self.alive[i]:
                continue
            if len(S):
                dd = np.hypot(self.s_x[S] - self.x[i], self.s_y[S] - self.y[i])
                a = int(dd.argmin())
                if dd[a] < 40:
                    k = int(S[a])
                    if self.coop[i] > 0.35:                 # welcomed: the band joins, bringing what it knows
                        self.s_pop[k] += self.size[i]
                        self.s_tools[k] = max(self.s_tools[k], self.tools[i]); self.s_lang[k] = max(self.s_lang[k], self.lang[i])
                        self.s_art[k] = max(self.s_art[k], self.art[i])
                        self.alive[i] = False
                    continue
                if dd[a] < 90:
                    continue                                 # too close to found a place of its own
            gx, gy = int(np.clip(self.x[i] / W * GX, 0, GX - 1)), int(np.clip(self.y[i] / H * GY, 0, GY - 1))
            if prod[gy, gx] > 0.6 and not ice[gy, gx] and self.size[i] >= 15:
                if self._found(i) is not None:
                    S = np.flatnonzero(self.s_alive)
        if not len(S):
            return
        # trade routes: towns with traders, within a few days' walk, are joined by a road
        # each place with traders keeps roads to its two nearest neighbours within reach
        trading = set(int(k) for k in S[self.s_roles[S, 3] > 0.005])
        nl = {int(k): 0 for k in S}
        links = set()
        P = np.stack([self.s_x[S], self.s_y[S]], 1)
        Dm = np.hypot(P[:, None, 0] - P[None, :, 0], P[:, None, 1] - P[None, :, 1])
        for a in range(len(S)):
            i = int(S[a])
            near = [b for b in np.argsort(Dm[a]) if b != a and Dm[a, b] < 260]
            nl[i] = len(near)                                # neighbours a trader could reach
            if i in trading:
                for b in near[:2]:
                    j = int(S[b])
                    links.add((min(i, j), max(i, j)))
        links = sorted(links)
        self.s_links = links
        for i, j in links:                                   # knowledge travels the roads
            for arr in (self.s_tools, self.s_lang, self.s_art):
                hi, lo = (i, j) if arr[i] >= arr[j] else (j, i)
                arr[lo] += 0.3 * (arr[hi] - arr[lo])
        nlinks = {int(k): 0 for k in S}
        for i, j in links:
            nlinks[i] += 1; nlinks[j] += 1
        for k in S:
            k = int(k)
            gx, gy = int(np.clip(self.s_x[k] / W * GX, 0, GX - 1)), int(np.clip(self.s_y[k] / H * GY, 0, GY - 1))
            here, iced = float(prod[gy, gx]), bool(ice[gy, gx])
            pop0 = float(self.s_pop[k])
            roles = self.s_roles[k]
            # surplus: food one farmer grows, against what one person eats; toolmakers make farmers better at it
            R = here * 2.4 * (1 + 0.04 * self.s_tools[k]) ** 0.5 * (1 + 0.8 * roles[0] / 0.07)
            smax = float(np.clip(1 - 1 / max(R, 0.01), 0, 0.55))
            unl = self._unlocked(k, nl[k])
            n = int(unl.sum())
            target = np.where(unl, min(smax, 0.07 * n) / max(1, n), 0.0)
            before = roles > 0.005
            roles += 0.08 * (target - roles)
            roles[roles < 0.002] = 0
            for r in np.flatnonzero((roles > 0.005) & ~before):
                self.milestone(f"trade_{ROLES[r]}", f"For the first time, a settlement of {int(pop0)} people keeps {ROLES[r]}: there is food enough to spare their hands.")
            ntr = int((roles > 0.005).sum())
            # what the place can carry: land, tools, its trades, its houses and its roads
            housing = 1 + min(1.0, 0.0004 * float(self.s_built[k]))
            K = 120 * here * (1 + 0.5 * math.log1p(self.s_tools[k] / 10)) * (1 + 0.12 * ntr) * housing * (1 + 0.08 * min(3, nlinks[k]))
            g = 0.006 * (1 - pop0 / max(K, 1)) - (0.06 if iced else 0)
            self.s_pop[k] = max(0.0, pop0 * (1 + float(np.clip(g, -0.12, 0.03))) + rng.normal(0, 0.3))
            dn = float(self.s_pop[k]) - pop0
            if dn > 0:
                self.l_born += dn
            else:
                self.l_died -= dn
            # builders build, faster with better tools; what is built slowly weathers
            self.s_built[k] = self.s_built[k] * 0.9998 + float(self.s_pop[k]) * float(roles[1]) * 0.004 * (1 + 0.05 * math.sqrt(self.s_tools[k]))
            b, has, old = float(self.s_built[k]), roles > 0.005, int(self.s_tier[k])
            # a place keeps its standing until it has clearly lost it (a fifth below the mark, or the trade gone)
            def reach(t, thr, need):
                return (b >= thr or (old >= t and b >= 0.8 * thr)) and all(has[r] for r in need)
            tier = 1
            if reach(2, 40, ()):
                tier = 2
            if tier == 2 and reach(3, 200, (2,)):
                tier = 3
            if tier == 3 and reach(4, 800, (3, 4)):
                tier = 4
            if tier == 4 and reach(5, 3000, (5, 6)):
                tier = 5
            if tier != old:
                self.s_tier[k] = tier
                if tier > old:
                    self.event("growth", f"A settlement has grown into a {TIERS[tier]}.")
                    self.milestone(f"tier{tier}", {2: "A hamlet has become a village: square houses, tilled fields and a granary for the surplus.",
                                                   3: "A village has raised a palisade around its houses and workshops.",
                                                   4: "A town stands: stone walls, a market where traders meet, and a temple.",
                                                   5: "A city: a citadel, a forge, a monument, and scribes to keep its accounts."}.get(tier, ""))
                else:
                    self.event("decline", f"A {TIERS[old]} has dwindled into a {TIERS[tier]}.")
            # invention: many minds, and toolmakers, make it faster than in any band
            p = 0.0004 * math.sqrt(min(float(self.s_pop[k]), 2000)) * (1 + 2 * self.s_lang[k]) * (1 + 6 * float(roles[0])) / (1 + 0.25 * self.s_tools[k])
            if rng.random() < p:
                self.s_tools[k] += 1
            if roles[4] > 0.005 and rng.random() < 0.01:
                self.s_art[k] += 1
            self.s_lang[k] = min(1.0, self.s_lang[k] + 0.0005 * (1 - self.s_lang[k]))
            # the crowded send people out: a farming band goes to find land of its own
            if self.s_pop[k] > 0.95 * K and self.s_pop[k] > 120 and rng.random() < 0.03:
                ang = rng.uniform(0, 2 * math.pi)
                j = self._band(self.s_x[k] + 70 * math.cos(ang), self.s_y[k] + 45 * math.sin(ang), 25.0, float(self.s_tools[k]), True,
                               float(self.s_lang[k]), float(self.s_art[k]), float(np.clip(self.s_coop[k] + rng.normal(0, 0.08), 0, 1)), int(self.s_lin[k]))
                if j is not None:
                    self.farm[j] = True
                    self.s_pop[k] -= 25
            # collapse: too few to keep the place; its ruins keep what it knew
            if self.s_pop[k] < 12:
                self.s_alive[k] = False
                self.l_died += float(self.s_pop[k])
                self.ruins.append([float(self.s_x[k]), float(self.s_y[k]), float(self.s_tools[k]), float(self.s_art[k]), True,
                                   float(self.s_lang[k]), 0, int(self.s_tier[k])])
                self.collapses += 1
                if self.s_tier[k] >= 3:
                    self.event("collapse", f"A {TIERS[int(self.s_tier[k])]} has been abandoned. Its walls stand empty.")
        # nomads and settlements: friends trade what they know, strangers raid (walls keep raiders out)
        A = np.flatnonzero(self.alive)
        S = np.flatnonzero(self.s_alive)
        if len(A) and len(S):
            for k in S:
                dd = np.hypot(self.x[A] - self.s_x[k], self.y[A] - self.s_y[k])
                for a in np.flatnonzero(dd < 30)[:3]:
                    i = int(A[a])
                    if self.coop[i] > 0.45 and self.s_coop[k] > 0.45:
                        self.tools[i] = max(self.tools[i], self.s_tools[k] - 1)
                        self.lang[i] = max(self.lang[i], self.s_lang[k] * 0.9)
                        self.s_tools[k] = max(self.s_tools[k], self.tools[i])
                    elif self.s_tier[k] >= 3:
                        self.l_died += 0.15 * float(self.size[i])
                        self.size[i] *= 0.85
                    else:
                        self.l_died += 0.03 * float(self.s_pop[k])
                        self.s_pop[k] *= 0.97

    def _lysis_init(self):
        if not hasattr(self, "ruins"):
            self.ruins = []                  # [x, y, tools, art, fire, lang, age]
            self.finds = []                  # [x, y, age] recent rediscoveries
            self.l_born = self.l_died = self.l_back = 0
            self.collapses = 0

    def lysis_counts(self):
        self._lysis_init()
        town = float(self.s_pop[self.s_alive].sum()) if hasattr(self, "s_alive") else 0.0
        return (int(self.l_born), int(self.l_died), int(getattr(self, "l_returned", 0.0)),
                int(self.size[self.alive].sum() + town) + 50)

    def _band(self, x, y, size, tools, fire, lang, art, coop, lin):
        free = np.flatnonzero(~self.alive)
        if not len(free):
            return None
        i = int(free[0])
        self._lysis_init()
        self.alive[i] = True
        if hasattr(self, "farm"):
            self.farm[i] = False
        self.x[i], self.y[i], self.size[i] = np.clip(x, 5, W - 5), np.clip(y, 5, H - 5), size
        self.tools[i], self.fire[i], self.lang[i], self.art[i], self.coop[i] = tools, fire, lang, art, coop
        if lin is None:
            lin = self.next_lin
            self.next_lin += 1
        self.lin[i] = lin
        return i

    def temp(self):
        t = self.tick
        cycle = 0.55 * math.sin(2 * math.pi * t / 36000) + 0.25 * math.sin(2 * math.pi * t / 9000 + 1.0)
        return float(cycle + 0.6 * self.dial("climate"))        # -1 deep ice age .. +1 warm

    def field(self):
        temp = self.temp()
        ice_line = 0.38 - 0.32 * temp                          # how far south the ice reaches (0..1 of the map)
        ice = self.lat < ice_line
        cold = np.clip((ice_line + 0.2 - self.lat) / 0.2, 0, 1)
        prod = self.base * (1 - 0.75 * cold) * mult(self.dial("bounty"), 1.8)
        prod[ice] = 0.02
        return prod.astype(np.float32), ice, cold

    def _step(self):
        if self.tick % 2:
            return
        rng = self.rng
        self._civ_init()
        A = np.flatnonzero(self.alive)
        if len(A) < 3:
            for _ in range(5):
                self._band(rng.uniform(400, 800), rng.uniform(470, 600), 18, 0, False, 0, 0, rng.uniform(0.3, 0.7), None)
            self.event("arrivals", "Humanity was down to a handful of bands. New bands wander in from the south.")
            A = np.flatnonzero(self.alive)
        prod, ice, cold = self.field()
        gx = np.clip((self.x[A] / W * GX).astype(int), 0, GX - 1)
        gy = np.clip((self.y[A] / H * GY).astype(int), 0, GY - 1)
        here = prod[gy, gx]
        crowd = np.zeros((GY, GX), np.float32)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                np.add.at(crowd, (np.clip(gy + dy, 0, GY - 1), np.clip(gx + dx, 0, GX - 1)), 1.0)
        # move toward kinder, emptier land nearby, with some wandering
        for a, i in enumerate(A):
            best, bx, by = here[a] - 0.12 * (crowd[gy[a], gx[a]] - 1), 0, 0
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = min(GX - 1, max(0, gx[a] + 2 * dx)), min(GY - 1, max(0, gy[a] + 2 * dy))
                v = prod[ny, nx] - 0.12 * crowd[ny, nx]
                if v > best + 0.02:
                    best, bx, by = v, dx, dy
            self.x[i] += 1.4 * bx + rng.normal(0, 1.0)
            self.y[i] += 1.4 * by + rng.normal(0, 1.0)
        self.x[A] = np.clip(self.x[A], 5, W - 5)
        self.y[A] = np.clip(self.y[A], 5, H - 5)
        # food, growth, cold
        size = self.size[A]
        chill = cold[gy, gx] * np.where(self.fire[A], 0.15, 1.0)
        # what the land can carry, raised by tools and talk (with diminishing returns), lowered by cold without fire
        K = 46 * here * (1 + 0.08 * self.tools[A]) ** 0.5 * (1 + 0.2 * self.lang[A]) * (1 - 0.7 * chill) / (1 + 0.1 * (crowd[gy, gx] - 1))
        growth = 0.006 * (1 - size / np.maximum(K, 1)) - 0.003 * chill
        self.size[A] = size * (1 + np.clip(growth, -0.05, 0.02)) + rng.normal(0, 0.15, len(A))
        dn = self.size[A] - size                          # for the gauge: people born and people lost
        self._lysis_init()
        self.l_born += float(dn[dn > 0].sum())
        self.l_died += float(-dn[dn < 0].sum())
        # invention and loss
        for a, i in enumerate(A):
            n = float(self.size[i])
            p = 0.000035 * min(n, 60) * (1 + 2 * self.lang[i]) / (1 + 0.25 * self.tools[i])
            if rng.random() < p:
                k = rng.random()
                if k < 0.5:
                    self.tools[i] += 1
                    if self.tools[i] >= 5:
                        self.milestone("tools5", "A band has reached a fifth level of tool-making, each built on the last.")
                    for lvl in (12, 25, 50, 100, 200):
                        if self.tools[i] >= lvl:
                            self.milestone(f"tools{lvl}", f"A band's tool-making has reached level {lvl}, each level standing on the ones before.")
                elif k < 0.65 and not self.fire[i] and self.tools[i] >= 2:
                    self.fire[i] = True
                    self.milestone("fire", "A band has learned to keep fire. The cold can be faced now.")
                elif k < 0.9:
                    self.lang[i] = min(1.0, self.lang[i] + 0.035 * (1.05 - self.lang[i]))
                    if self.lang[i] >= 0.5:
                        self.milestone("language", "A band's talk has become rich enough to pass on more than it shows: language.")
                elif self.lang[i] >= 0.6 and n > 30:
                    self.art[i] += 1
                    self.milestone("art", "A band has begun to make images. Nobody needed them; they made them anyway.")
            if n < 16 and rng.random() < 0.002 * (16 - n) / 16:      # the small band forgets
                if self.tools[i] > 0:
                    self.tools[i] -= 1
                elif self.art[i] > 0:
                    self.art[i] -= 1
                if rng.random() < 0.15:
                    self.fire[i] = False
                self.lang[i] = max(0.0, self.lang[i] - 0.02)
        # farming: a band that knows enough, on kind land, may learn to sow what it gathers
        cand = A[(~self.farm[A]) & (self.tools[A] >= 10) & (self.lang[A] >= 0.45) & (here > 0.65)]
        if len(cand):
            got = cand[rng.random(len(cand)) < 0.0004 * mult(self.dial("bounty"), 1.5)]
            if len(got):
                self.farm[got] = True
                self.milestone("farming", "A band has learned to sow what it gathers. It can stay in one place now.")
        # meetings
        if len(A) > 1 and self.tick % 6 == 0:
            from scipy.spatial import cKDTree
            pairs = cKDTree(np.stack([self.x[A], self.y[A]], 1)).query_pairs(26.0, output_type="ndarray")
            for a, b in pairs[:30]:
                i, j = int(A[a]), int(A[b])
                if not (self.alive[i] and self.alive[j]):
                    continue
                if self.coop[i] > 0.45 and self.coop[j] > 0.45:
                    for arr in (self.tools, self.lang, self.art):
                        m = max(arr[i], arr[j])
                        arr[i] = arr[j] = m - (0.3 if arr is self.tools and rng.random() < 0.2 else 0)
                    self.fire[i] = self.fire[j] = self.fire[i] or self.fire[j]
                    self.farm[i] = self.farm[j] = self.farm[i] or self.farm[j]
                else:
                    loser = i if self.size[i] < self.size[j] else j
                    self.l_died += 0.15 * float(self.size[loser])
                    self.size[loser] *= 0.85
        # splitting and dying
        for i in np.flatnonzero(self.alive & (self.size > 44))[:3]:
            if self.alive.all():
                break
            self.size[i] *= 0.5
            ang = rng.uniform(0, 2 * math.pi)
            j = self._band(self.x[i] + 40 * math.cos(ang), self.y[i] + 30 * math.sin(ang), float(self.size[i]), float(self.tools[i]),
                           bool(self.fire[i]), float(self.lang[i]), float(self.art[i]),
                           float(np.clip(self.coop[i] + rng.normal(0, 0.08), 0, 1)), int(self.lin[i]))
            if j is not None:
                self.farm[j] = self.farm[i]
        dead = np.flatnonzero(self.alive & (self.size < 3))
        self.alive[dead] = False
        self.l_died += float(self.size[dead].sum())
        for i in dead:                                    # the camp is left behind, holding what the band knew
            if self.tools[i] >= 1 or self.art[i] > 0:
                self.ruins.append([float(self.x[i]), float(self.y[i]), float(self.tools[i]), float(self.art[i]),
                                   bool(self.fire[i]), float(self.lang[i]), 0])
                self.collapses += 1
        self.ruins = sorted(self.ruins, key=lambda r: -r[2])[:50]
        # ruins weather slowly (not under ice, which keeps them); a band camping on a ruin of people who knew more learns
        if self.ruins and self.tick % 10 == 0:
            A = np.flatnonzero(self.alive)
            keep = []
            for r in self.ruins:
                rx, ry = int(np.clip(r[0] / W * GX, 0, GX - 1)), int(np.clip(r[1] / H * GY, 0, GY - 1))
                r[6] += 10
                if not ice[ry, rx]:
                    r[2] -= 0.004
                found = False
                if len(A) and not ice[ry, rx]:
                    dd = np.hypot(self.x[A] - r[0], self.y[A] - r[1])
                    a = int(dd.argmin())
                    i = int(A[a])
                    if dd[a] < 22 and r[2] > self.tools[i] + 1:
                        gain = 0.5 * (r[2] - self.tools[i])
                        self.tools[i] += gain
                        self.art[i] = max(self.art[i], r[3])
                        self.lang[i] = max(self.lang[i], 0.8 * r[5])
                        if r[4] and not self.fire[i]:
                            self.fire[i] = True
                        self.l_back += 1
                        self.l_returned = getattr(self, "l_returned", 0.0) + 5.0 * gain
                        self.finds.append([r[0], r[1], 0])
                        found = True
                        self.milestone("rediscovery", "A band has camped among the ruins of people who knew more, and learned from what they left.")
                if not found and r[2] > 0.5:
                    keep.append(r)
            self.ruins = keep
        for f in self.finds:
            f[2] += 2
        self.finds = [f for f in self.finds if f[2] < 200]
        if self.tick % 10 == 0:
            self._civ(prod, ice)
        if self.alive.any() and float(self.size[self.alive].sum()) > 2000:
            self.milestone("people2000", "There are now two thousand people.")

    def stats(self):
        A = np.flatnonzero(self.alive)
        prod, ice, cold = self.field()
        self._civ_init()
        S = np.flatnonzero(self.s_alive)
        town = float(self.s_pop[S].sum()) if len(S) else 0.0
        ntr = (self.s_roles[S] > 0.005).sum(1) if len(S) else np.zeros(1)
        out = {"bands": int(len(A)), "people": int((self.size[A].sum() if len(A) else 0) + town), "ice": int(round(100 * float(ice.mean()))),
               "ruins": len(getattr(self, "ruins", [])), "rediscoveries": int(getattr(self, "l_back", 0)),
               "settlements": int(len(S)), "townsfolk": int(town), "trades": int(ntr.max()) if len(S) else 0,
               "trades_x100": int(100 * ntr.max()) if len(S) else 0,
               "tier_max": int(self.s_tier[S].max()) if len(S) else 0, "biggest": int(self.s_pop[S].max()) if len(S) else 0,
               "farming": int(round(100 * float(self.farm[A].mean()))) if len(A) else 0}
        if len(A):
            gx = np.clip((self.x[A] / W * GX).astype(int), 0, GX - 1)
            gy = np.clip((self.y[A] / H * GY).astype(int), 0, GY - 1)
            occ = np.zeros((GY, GX), bool)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    occ[np.clip(gy + dy, 0, GY - 1), np.clip(gx + dx, 0, GX - 1)] = True
            out.update({"tools_max": int(self.tools[A].max()), "tools_mean": round(float(self.tools[A].mean()), 2),
                        "fire": int(round(100 * float(self.fire[A].mean()))), "language": round(float(self.lang[A].mean()), 3),
                        "language_x10": round(10 * float(self.lang[A].mean()), 2), "art": int(round(100 * float((self.art[A] > 0).mean()))),
                        "range": int(round(100 * float((occ & ~ice).sum() / max(1, (~ice).sum()))))})
        return out

    def stratum(self):
        A = np.flatnonzero(self.alive)
        if not len(A):
            return {"cols": []}
        l, idx = np.unique(self.lin[A], return_inverse=True)
        n = np.bincount(idx, weights=self.size[A])
        top = np.argsort(-n)[:6]
        return {"cols": [[round((int(l[k]) * 0.618034) % 1, 3), 0.7, int(n[k])] for k in top]}

    def frame(self):
        prod, ice, cold = self.field()
        A = np.flatnonzero(self.alive)
        zone = np.where(ice, 0, np.where(cold > 0.5, 1, np.where(prod < 0.45, 2, np.where(prod < 0.8, 3, 4))))
        return {"w": W, "h": H, "gx": GX, "gy": GY, "zones": zone.astype(int).ravel().tolist(), "temp": round(self.temp(), 3),
                "bands": [[int(i), round(float(self.x[i]), 1), round(float(self.y[i]), 1), int(self.size[i]), int(self.tools[i]),
                           int(self.fire[i]), round(float(self.lang[i]), 2), int(self.art[i]), round((int(self.lin[i]) * 0.618034) % 1, 3),
                           int(self.farm[i]) if hasattr(self, "farm") else 0]
                          for i in A],
                "ruins": [[round(r[0], 1), round(r[1], 1), int(r[2]), int(r[3]), int(r[4]),
                           int(ice[int(np.clip(r[1] / H * GY, 0, GY - 1)), int(np.clip(r[0] / W * GX, 0, GX - 1))]),
                           int(r[7]) if len(r) > 7 else 0]
                          for r in getattr(self, "ruins", [])],
                "towns": [[int(self.s_id[k]), round(float(self.s_x[k]), 1), round(float(self.s_y[k]), 1), int(self.s_pop[k]),
                           int(self.s_tier[k]), round(float(self.s_built[k]), 1), [round(float(v), 3) for v in self.s_roles[k]],
                           int(self.s_tools[k]), round((int(self.s_lin[k]) * 0.618034) % 1, 3), int(self.tick - self.s_found[k])]
                          for k in np.flatnonzero(getattr(self, "s_alive", np.zeros(0, bool)))],
                "roads": [[round(float(self.s_x[i]), 1), round(float(self.s_y[i]), 1), round(float(self.s_x[j]), 1), round(float(self.s_y[j]), 1)]
                          for i, j in getattr(self, "s_links", [])],
                "finds": [[round(f[0], 1), round(f[1], 1), f[2]] for f in getattr(self, "finds", [])]}
