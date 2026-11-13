"""Builds Mizan, the chatbot's Lottie mascot -> widget/public/mizan.json

One file, one timeline, one segment per state (see SEGMENTS / markers).
The widget plays "<state>_in" once (if it exists), then loops "<state>".
Everything is drawn in comp coordinates (400x400); each layer pivots around
its own anchor so positions stay readable.
"""
import json
from pathlib import Path

FPS = 30
W = H = 400

SEGMENTS = [  # name, length in frames
    ("idle", 90),
    ("listen_in", 10), ("listen", 60),
    ("think_in", 10), ("think", 80),
    ("talk_in", 6), ("talk", 60),
    ("happy", 60),
    ("sad", 60),
    ("refuse", 60),
]
START = {}
_t = 0
for _n, _l in SEGMENTS:
    START[_n] = _t
    _t += _l
OP = _t
LEN = dict(SEGMENTS)


def hexc(h, a=1):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [a]


GREEN = "#1E7B53"
GREEN_D = "#145C3D"
GREEN_DD = "#0F3D29"
CREAM = "#EEF5E8"
GOLD = "#D99A1E"
RED = "#C1272D"
RED_D = "#8E1B20"
INK = "#15211B"
MOUTH = "#6B1E1E"
PINK = "#FF9DAA"
TEAR = "#7CC4F2"


# ---------- animated properties ----------
class Track:
    """Keyframes per segment: {"segment": [(frame_in_segment, value), ...]}.
    Segments not listed hold the default. Each segment begins and ends on
    its own keys, so jumping between segments never interpolates across them."""

    def __init__(self, default, **segs):
        self.default = default
        self.segs = segs

    def compile(self, spatial=False):
        if not self.segs:
            return {"a": 0, "k": self.default}
        keys = []
        for name, length in SEGMENTS:
            ks = list(self.segs.get(name) or [(0, self.default)])
            if ks[0][0] != 0:
                ks.insert(0, (0, ks[0][1]))
            if ks[-1][0] < length - 1:
                ks.append((length - 1, ks[-1][1]))
            for f, v in ks:
                keys.append((START[name] + f, v, name))
        out = []
        for i, (t, v, seg) in enumerate(keys):
            k = {"t": t, "s": v if isinstance(v, list) else [v]}
            last_of_seg = i + 1 < len(keys) and keys[i + 1][2] != seg
            if last_of_seg:
                k["h"] = 1  # hold: no blend into the next segment
            elif i + 1 < len(keys):
                n = 1 if spatial else len(k["s"]) if isinstance(v, list) and not isinstance(v[0], dict) else 1
                k["o"] = {"x": [0.42] * n, "y": [0] * n}
                k["i"] = {"x": [0.58] * n, "y": [1] * n}
            out.append(k)
        return {"a": 1, "k": out}


def P(v):
    return v.compile() if isinstance(v, Track) else {"a": 0, "k": v}


def layer_ks(pivot, pos=None, scale=None, rot=None, op=None):
    """pos: Track/list of [dx, dy] OFFSETS from pivot."""
    px, py = pivot
    if isinstance(pos, Track):
        conv = lambda d: [px + d[0], py + d[1]]
        p = Track(conv(pos.default), **{s: [(f, conv(v)) for f, v in ks] for s, ks in pos.segs.items()}).compile(spatial=True)
    else:
        d = pos or [0, 0]
        p = {"a": 0, "k": [px + d[0], py + d[1]]}
    return {
        "o": P(op if op is not None else 100),
        "r": P(rot if rot is not None else 0),
        "p": p,
        "a": {"a": 0, "k": [px, py]},
        "s": P(scale if scale is not None else [100, 100]),
    }


# ---------- shapes ----------
def tr(p=(0, 0), a=(0, 0), s=(100, 100), r=0, o=100):
    return {"ty": "tr", "p": P(list(p)), "a": P(list(a)), "s": P(list(s) if not isinstance(s, Track) else s),
            "r": P(r), "o": P(o), "sk": {"a": 0, "k": 0}, "sa": {"a": 0, "k": 0}}


def ell(c, size):
    return {"ty": "el", "p": {"a": 0, "k": list(c)}, "s": {"a": 0, "k": list(size)}, "d": 1}


def rect(c, size, r):
    return {"ty": "rc", "p": {"a": 0, "k": list(c)}, "s": {"a": 0, "k": list(size)}, "r": {"a": 0, "k": r}, "d": 1}


def path(v, i=None, o=None, closed=True):
    z = [[0, 0]] * len(v)
    return {"i": i or z, "o": o or z, "v": v, "c": closed}


def sh(p):
    return {"ty": "sh", "ks": P(p) if isinstance(p, Track) else {"a": 0, "k": p}}


def fill(color, a=1, o=100):
    return {"ty": "fl", "c": {"a": 0, "k": hexc(color, a)}, "o": P(o), "r": 1}


def stroke(color, w, o=100):
    return {"ty": "st", "c": {"a": 0, "k": hexc(color)}, "o": P(o), "w": {"a": 0, "k": w}, "lc": 2, "lj": 2}


def group(name, *items, t=None):
    return {"ty": "gr", "nm": name, "it": list(items) + [t or tr()]}


_ind = [0]
LAYERS = []


def add_layer(name, shapes, ks, parent=None):
    _ind[0] += 1
    L = {"ddd": 0, "ind": _ind[0], "ty": 4, "nm": name, "sr": 1, "ks": ks, "ao": 0,
         "shapes": shapes, "ip": 0, "op": OP, "st": 0, "bm": 0}
    if parent:
        L["parent"] = parent
    LAYERS.append(L)
    return _ind[0]


def mouth(w, y0, yt, yb, cx=200):
    h = w / 3
    v = [[cx - w / 2, y0], [cx, yt], [cx + w / 2, y0], [cx, yb]]
    i = [[0, 0], [-h, 0], [0, 0], [h, 0]]
    o = [[0, 0], [h, 0], [0, 0], [-h, 0]]
    return path(v, i, o)


def star(cx, cy, r):
    v = [[cx, cy - r], [cx + r * .28, cy - r * .28], [cx + r, cy], [cx + r * .28, cy + r * .28],
         [cx, cy + r], [cx - r * .28, cy + r * .28], [cx - r, cy], [cx - r * .28, cy - r * .28]]
    return path(v)


# ============ timeline values ============
# body: bob / lean / jump (pivot = feet)
body_pos = Track([0, 0],
    idle=[(0, [0, 0]), (45, [0, -6]), (89, [0, 0])],
    listen_in=[(0, [0, 0]), (9, [0, 2])],
    listen=[(0, [0, 2]), (30, [0, 5]), (59, [0, 2])],
    think_in=[(0, [0, 0]), (9, [0, -3])],
    think=[(0, [0, -3]), (40, [0, -7]), (79, [0, -3])],
    talk_in=[(0, [0, 0]), (5, [0, -2])],
    talk=[(0, [0, -2]), (15, [0, -5]), (30, [0, -2]), (45, [0, -5]), (59, [0, -2])],
    happy=[(0, [0, 0]), (6, [0, 4]), (18, [0, -46]), (30, [0, 2]), (38, [0, -8]), (46, [0, 0])],
    sad=[(0, [0, 0]), (14, [0, 8])],
    refuse=[(0, [0, 0]), (8, [0, 2])],
)
body_scale = Track([100, 100],
    happy=[(0, [100, 100]), (6, [110, 90]), (16, [94, 107]), (30, [108, 92]), (40, [100, 100])],
    sad=[(0, [100, 100]), (14, [103, 95])],
    talk=[(0, [100, 100]), (15, [101, 99]), (30, [100, 100]), (45, [101, 99]), (59, [100, 100])],
)
body_rot = Track(0,
    listen_in=[(0, 0), (9, -4)], listen=[(0, -4), (30, -5), (59, -4)],
    think_in=[(0, 0), (9, 3)], think=[(0, 3), (40, 5), (79, 3)],
    refuse=[(0, 0), (8, -7), (16, 7), (24, -7), (32, 7), (40, -3), (48, 0)],
)
shadow_scale = Track([100, 100],
    happy=[(0, [100, 100]), (6, [108, 100]), (18, [62, 70]), (30, [108, 100]), (40, [100, 100])],
)

# eyes: blink by scaling Y (pupils are children, so they blink too)
blink = lambda f: [(f, [100, 100]), (f + 3, [100, 8]), (f + 6, [100, 100])]
eyes_scale = Track([100, 100],
    idle=[(0, [100, 100])] + blink(58),
    listen=[(0, [100, 104])],
    listen_in=[(0, [100, 100]), (9, [100, 104])],
    think=[(0, [100, 100])] + blink(50),
    talk=[(0, [100, 100])] + blink(40),
    sad=[(0, [100, 100]), (14, [100, 86])],
    refuse=[(0, [100, 100]), (8, [100, 78])],
)
eyes_op = Track(100, happy=[(0, 100), (3, 0), (52, 0), (56, 100)])
happy_eyes_op = Track(0, happy=[(0, 0), (3, 100), (52, 100), (56, 0)])

pupils = Track([0, 0],
    idle=[(0, [0, 0]), (20, [0, 0]), (26, [-6, 1]), (40, [-6, 1]), (46, [5, 1]), (60, [5, 1]), (66, [0, 0])],
    listen_in=[(0, [0, 0]), (9, [-3, 9])], listen=[(0, [-3, 9]), (30, [1, 9]), (59, [-3, 9])],
    think_in=[(0, [0, 0]), (9, [7, -10])], think=[(0, [7, -10]), (40, [3, -11]), (79, [7, -10])],
    talk=[(0, [0, 2])], talk_in=[(0, [0, 0]), (5, [0, 2])],
    sad=[(0, [0, 0]), (14, [-2, 8])],
    refuse=[(0, [0, 0]), (8, [0, 3])],
)

brow_y = Track([0, 0],
    listen_in=[(0, [0, 0]), (9, [0, -6])], listen=[(0, [0, -6])],
    think_in=[(0, [0, 0]), (9, [0, -9])], think=[(0, [0, -9]), (40, [0, -11]), (79, [0, -9])],
    talk=[(0, [0, -3]), (15, [0, -6]), (30, [0, -3]), (45, [0, -6]), (59, [0, -3])], talk_in=[(0, [0, 0]), (5, [0, -3])],
    happy=[(0, [0, 0]), (6, [0, -8]), (50, [0, -8]), (59, [0, 0])],
    sad=[(0, [0, 0]), (14, [0, -3])],
    refuse=[(0, [0, 0]), (8, [0, 5])],
)
brow_l_rot = Track(0, sad=[(0, 0), (14, -16)], refuse=[(0, 0), (8, 18)], think_in=[(0, 0), (9, -6)], think=[(0, -6)])
brow_r_rot = Track(0, sad=[(0, 0), (14, 16)], refuse=[(0, 0), (8, -18)], think_in=[(0, 0), (9, 4)], think=[(0, 4)])

M_SMILE = mouth(40, 262, 265, 275)
M_TALK_A = mouth(30, 266, 258, 286)
M_TALK_B = mouth(38, 264, 262, 278)
M_HAPPY = mouth(58, 256, 258, 294)
M_SAD = mouth(34, 278, 266, 271)
M_FLAT = mouth(32, 271, 269, 274)
M_HMM = mouth(22, 270, 268, 274, cx=212)
M_LISTEN = mouth(26, 264, 266, 280)
mouth_shape = Track([M_SMILE],
    listen_in=[(0, [M_SMILE]), (9, [M_LISTEN])], listen=[(0, [M_LISTEN])],
    think_in=[(0, [M_SMILE]), (9, [M_HMM])], think=[(0, [M_HMM])],
    talk_in=[(0, [M_SMILE]), (5, [M_TALK_B])],
    talk=[(0, [M_TALK_B]), (5, [M_TALK_A]), (10, [M_TALK_B]), (16, [M_TALK_A]), (22, [M_SMILE]), (27, [M_TALK_A]),
          (33, [M_TALK_B]), (39, [M_TALK_A]), (45, [M_TALK_B]), (51, [M_TALK_A]), (59, [M_TALK_B])],
    happy=[(0, [M_SMILE]), (5, [M_HAPPY]), (50, [M_HAPPY]), (59, [M_SMILE])],
    sad=[(0, [M_SMILE]), (14, [M_SAD])],
    refuse=[(0, [M_SMILE]), (8, [M_FLAT])],
)
cheek_op = Track(75, happy=[(0, 75), (6, 100), (50, 100), (59, 75)], sad=[(0, 75), (14, 30)], refuse=[(0, 75), (8, 30)])

# arms rotate around the shoulders
arm_l = Track(0,
    idle=[(0, 0), (45, 6), (89, 0)],
    talk=[(0, 0), (15, 14), (30, 0), (45, 14), (59, 0)],
    happy=[(0, 0), (6, 125), (12, 140), (18, 120), (24, 140), (40, 125), (54, 0)],
    sad=[(0, 0), (14, -12)],
    refuse=[(0, 0), (8, 18)],
)
arm_r = Track(0,
    idle=[(0, 0), (45, -6), (89, 0)],
    think_in=[(0, 0), (9, -150)], think=[(0, -150), (10, -160), (20, -148), (30, -160), (40, -150), (79, -150)],
    talk=[(0, 0), (15, -10), (30, -30), (45, -10), (59, 0)],
    happy=[(0, 0), (6, -125), (12, -140), (18, -120), (24, -140), (40, -125), (54, 0)],
    sad=[(0, 0), (14, 12)],
    refuse=[(0, 0), (8, -100), (48, -100), (59, 0)],
)

# fez + tassel
fez_rot = Track(-8, happy=[(0, -8), (18, -16), (30, -2), (46, -8)], refuse=[(0, -8), (16, -2), (32, -14), (48, -8)])
tassel_rot = Track(0,
    idle=[(0, -6), (45, 10), (89, -6)],
    listen=[(0, 0), (30, 6), (59, 0)],
    think=[(0, -10), (20, 14), (40, -10), (60, 14), (79, -10)],
    talk=[(0, -4), (15, 8), (30, -4), (45, 8), (59, -4)],
    happy=[(0, 0), (12, -40), (24, 35), (36, -20), (48, 10), (59, 0)],
    refuse=[(0, 0), (12, 25), (20, -25), (28, 25), (36, -25), (48, 0)],
)

# thinking dots + sparkles + tear
def dot_op(delay):
    return Track(0, think_in=[(0, 0)], think=[(0, 0), (delay, 0), (delay + 10, 100), (delay + 40, 100), (delay + 50, 0), (79, 0)])


def spark(delay):
    return Track([0, 0], happy=[(0, [0, 0]), (delay, [0, 0]), (delay + 8, [120, 120]), (delay + 14, [90, 90]),
                                (delay + 26, [100, 100]), (delay + 34, [0, 0])])


tear_op = Track(0, sad=[(0, 0), (16, 0), (22, 100), (50, 100), (58, 0)])
tear_pos = Track([0, 0], sad=[(0, [0, 0]), (20, [0, 0]), (52, [0, 30])])
stop_op = Track(0, refuse=[(0, 0), (10, 0), (16, 100), (46, 100), (54, 0)])

# ============ layers (first = on top) ============
add_layer("sparkles", [
    group("s1", sh(star(110, 140, 16)), fill(GOLD), t=tr((110, 140), (110, 140), spark(8))),
    group("s2", sh(star(300, 112, 12)), fill(GOLD), t=tr((300, 112), (300, 112), spark(14))),
    group("s3", sh(star(322, 210, 9)), fill(GOLD), t=tr((322, 210), (322, 210), spark(20))),
    group("s4", sh(star(84, 230, 8)), fill(GOLD), t=tr((84, 230), (84, 230), spark(4))),
], layer_ks((200, 200)))

add_layer("think_dots", [
    group("d1", ell((292, 118), (11, 11)), fill(GREEN), t=tr(o=dot_op(0))),
    group("d2", ell((314, 96), (15, 15)), fill(GREEN), t=tr(o=dot_op(12))),
    group("d3", ell((342, 74), (21, 21)), fill(GREEN), t=tr(o=dot_op(24))),
], layer_ks((200, 200)))

add_layer("shadow", [group("sh", ell((200, 352), (150, 18)), fill("#000000", o=14))],
          layer_ks((200, 352), scale=shadow_scale))

BODY = add_layer("body", [
    group("highlight", ell((150, 178), (56, 30)), fill("#FFFFFF", o=16), t=tr((150, 178), (150, 178), r=-28)),
    group("emblem",
          # tiny balance (mizan) on the belly
          {"ty": "sh", "ks": {"a": 0, "k": path([[200, 280], [200, 314]], closed=False)}},
          {"ty": "sh", "ks": {"a": 0, "k": path([[180, 286], [220, 286]], closed=False)}},
          {"ty": "sh", "ks": {"a": 0, "k": path([[180, 286], [174, 300], [186, 300]], closed=False)}},
          {"ty": "sh", "ks": {"a": 0, "k": path([[220, 286], [214, 300], [226, 300]], closed=False)}},
          {"ty": "sh", "ks": {"a": 0, "k": path([[190, 314], [210, 314]], closed=False)}},
          stroke(GOLD, 4)),
    group("belly", ell((200, 288), (118, 82)), fill(CREAM)),
    group("feet", ell((164, 343), (50, 22)), ell((236, 343), (50, 22)), fill(GREEN_D)),
    group("body", ell((200, 240), (212, 206)), fill(GREEN)),
], layer_ks((200, 345), pos=body_pos, scale=body_scale, rot=body_rot))

add_layer("arm_r", [group("arm", ell((304, 284), (34, 60)), fill(GREEN_D), t=tr((304, 284), (304, 284), r=-22))],
          layer_ks((290, 258), rot=arm_r), parent=BODY)
add_layer("arm_l", [group("arm", ell((96, 284), (34, 60)), fill(GREEN_D), t=tr((96, 284), (96, 284), r=22))],
          layer_ks((110, 258), rot=arm_l), parent=BODY)

add_layer("stop_hand", [group("palm", ell((330, 190), (30, 34)), fill(GREEN_D),
                              t=tr(o=stop_op))], layer_ks((200, 200)), parent=BODY)

TASSEL_HOST = add_layer("fez", [
    group("top", ell((206, 106), (64, 14)), fill("#D9363C")),
    group("band", sh(path([[166, 140], [248, 140], [250, 152], [164, 152]])), fill(RED_D)),
    group("fez", sh(path([[174, 106], [238, 106], [250, 152], [164, 152]])), fill(RED)),
], layer_ks((206, 150), rot=fez_rot), parent=BODY)
add_layer("tassel", [
    group("cord", {"ty": "sh", "ks": {"a": 0, "k": path([[206, 104], [244, 108], [254, 130]], [[0, 0], [-14, -4], [0, 0]], [[0, 0], [8, 2], [0, 0]], closed=False)}}, stroke(GOLD, 3)),
    group("tuft", sh(path([[254, 126], [263, 156], [245, 156]])), fill(GOLD)),
], layer_ks((206, 104), rot=tassel_rot), parent=TASSEL_HOST)

add_layer("tear", [group("t", ell((152, 248), (10, 14)), fill(TEAR), t=tr(o=tear_op))],
          layer_ks((152, 248), pos=tear_pos), parent=BODY)

add_layer("mouth", [group("m", sh(mouth_shape), fill(MOUTH))], layer_ks((200, 268)), parent=BODY)
add_layer("cheeks", [group("c", ell((146, 254), (28, 15)), ell((254, 254), (28, 15)), fill(PINK, o=cheek_op))],
          layer_ks((200, 254)), parent=BODY)

add_layer("brow_l", [group("b", rect((168, 182), (32, 8), 4), fill(GREEN_DD))],
          layer_ks((168, 182), pos=brow_y, rot=brow_l_rot), parent=BODY)
add_layer("brow_r", [group("b", rect((232, 182), (32, 8), 4), fill(GREEN_DD))],
          layer_ks((232, 182), pos=brow_y, rot=brow_r_rot), parent=BODY)

add_layer("happy_eyes", [
    group("l", {"ty": "sh", "ks": {"a": 0, "k": path([[152, 226], [168, 208], [184, 226]], [[0, 0], [-9, 0], [0, 0]], [[0, 0], [9, 0], [0, 0]], False)}}, stroke(INK, 7)),
    group("r", {"ty": "sh", "ks": {"a": 0, "k": path([[216, 226], [232, 208], [248, 226]], [[0, 0], [-9, 0], [0, 0]], [[0, 0], [9, 0], [0, 0]], False)}}, stroke(INK, 7)),
], layer_ks((200, 220), op=happy_eyes_op), parent=BODY)

EYES = add_layer("eyes", [
    group("whites", ell((168, 222), (50, 58)), ell((232, 222), (50, 58)), fill("#FFFFFF")),
], layer_ks((200, 222), scale=eyes_scale, op=eyes_op), parent=BODY)
# pupils sit above the whites; parented to the eyes so blinks squash them too
add_layer("pupils", [
    group("shine", ell((175, 218), (8, 8)), ell((239, 218), (8, 8)), fill("#FFFFFF")),
    group("p", ell((170, 226), (24, 28)), ell((234, 226), (24, 28)), fill(INK)),
], layer_ks((200, 226), pos=pupils, op=eyes_op), parent=EYES)
# the pupils must render above the whites -> move them before "eyes" in the list
LAYERS.insert(LAYERS.index(next(l for l in LAYERS if l["nm"] == "eyes")), LAYERS.pop())

# tassel in front of the fez
tassel = next(l for l in LAYERS if l["nm"] == "tassel")
LAYERS.remove(tassel)
LAYERS.insert(LAYERS.index(next(l for l in LAYERS if l["nm"] == "fez")), tassel)

# z-order: shadow at the very bottom, body just above it, everything else on top
# no ground shadow: the widget's own rule / page is the ground
shadow = next(l for l in LAYERS if l["nm"] == "shadow")
LAYERS.remove(shadow)
LAYERS.append(shadow)
LAYERS.remove(shadow)
# body must be below its face parts but above the shadow
body = next(l for l in LAYERS if l["nm"] == "body")
LAYERS.remove(body)
LAYERS.append(body)

# CSS hook: the widget nudges this layer so the eyes follow the mouse
for _l in LAYERS:
    if _l["nm"] == "pupils":
        _l["cl"] = "pupils"

doc = {
    "v": "5.7.4", "fr": FPS, "ip": 0, "op": OP, "w": W, "h": H, "nm": "Mizan", "ddd": 0,
    "assets": [], "layers": LAYERS,
    "markers": [{"tm": START[n], "cm": n, "dr": l} for n, l in SEGMENTS],
}
out = Path(__file__).resolve().parent.parent / "public" / "mizan.json"
out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
print(f"{out} — {OP} frames, {len(LAYERS)} layers, {out.stat().st_size // 1024} KB")
print({n: (START[n], START[n] + l) for n, l in SEGMENTS})
