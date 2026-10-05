#!/usr/bin/env python3
"""
Synthetic BPO contact-centre data generator.

ALL DATA PRODUCED HERE IS SYNTHETIC. No real customers, agents or company.

What it produces (into ./data/raw/, this is what the API serves):
    teams, agents, customers, interactions, surveys, qa_evaluations, shifts
The raw files are deliberately MESSY (duplicates, mixed date formats, inconsistent
text, nulls, invalid values...). Your job is to find and fix them.

Also produced (into ./answer_key/ -- DON'T OPEN UNTIL YOU HAVE FINISHED YOUR CLEANING):
    defect_log.json           how many of each defect type were injected
    truth_interactions.csv.gz the clean version of interactions, to check your work

Spoiler warning: the business story (what goes wrong in Q3) is planted in the
constants and functions below. Treat this file as a black box until you have done
your own analysis. It is deterministic: same seed = same data.

Usage:
    python generate_data.py                # default seed 42
    python generate_data.py --seed 7
"""
import argparse
import calendar
import csv
import gzip
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

START = date(2026, 4, 1)
END = date(2026, 9, 27)
END_DT = datetime(2026, 9, 27, 23, 59, 59)

# ---- planted story dates (spoilers) ----
GROWTH_START = date(2026, 7, 1)
MIGRATION = date(2026, 8, 1)
COMPLAINT_SPIKE = date(2026, 8, 5)
NEW_HIRE_START = date(2026, 7, 6)
ATTRITION = date(2026, 8, 15)

TEAMS = {
    1: dict(name="Billing Voice", channel="Voice", site="Cairo", cap=45, demand=150, headcount=6,
            cats={"Billing": 70, "Account Access": 10, "Product Inquiry": 10, "Delivery/Order": 10}),
    2: dict(name="Technical Voice", channel="Voice", site="Cairo", cap=36, demand=125, headcount=6,
            cats={"Technical": 65, "Account Access": 20, "Product Inquiry": 15}),
    3: dict(name="Chat Support", channel="Chat", site="Alexandria", cap=50, demand=150, headcount=6,
            cats={"Technical": 30, "Billing": 20, "Account Access": 15, "Delivery/Order": 15,
                  "Product Inquiry": 15, "Complaint": 5}),
    4: dict(name="Email Support", channel="Email", site="Alexandria", cap=55, demand=155, headcount=5,
            cats={"Billing": 25, "Delivery/Order": 25, "Complaint": 15, "Technical": 15,
                  "Product Inquiry": 10, "Cancellation": 10}),
    5: dict(name="Retention & Complaints", channel="Voice", site="Cairo", cap=30, demand=85, headcount=5,
            cats={"Complaint": 55, "Cancellation": 45}),
}

HANDLE_MEDIAN = {"Billing": 400, "Technical": 620, "Account Access": 330, "Delivery/Order": 380,
                 "Complaint": 560, "Product Inquiry": 240, "Cancellation": 500}
FCR_BASE = {"Billing": 0.80, "Technical": 0.72, "Account Access": 0.85, "Delivery/Order": 0.75,
            "Complaint": 0.60, "Product Inquiry": 0.88, "Cancellation": 0.70}
CH_HANDLE_MULT = {"Voice": 1.0, "Chat": 1.3, "Email": 1.1}
CH_FCR_ADJ = {"Voice": 0.0, "Chat": 0.02, "Email": -0.05}
WAIT_BASE = {"Voice": 9.0, "Chat": 15.0, "Email": 5400.0}   # seconds (email = first response time)
PATIENCE = {"Voice": 300.0, "Chat": 240.0}
PRIORITY_W = {"Complaint": [15, 40, 45], "Technical": [30, 45, 25], "Cancellation": [30, 40, 30]}

HOURS = {"Voice": list(range(8, 22)), "Chat": list(range(8, 22)), "Email": list(range(24))}
_HW = {"Voice": [3, 6, 9, 10, 9, 8, 7, 7, 8, 9, 8, 6, 4, 2],
       "Email": [1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 7, 6, 6, 6, 7, 7, 6, 5, 4, 3, 2, 2, 1]}
_HW["Chat"] = _HW["Voice"]


def _cum(ws):
    out, t = [], 0
    for w in ws:
        t += w
        out.append(t)
    return out


CUMW = {k: _cum(v) for k, v in _HW.items()}

FIRST = ["Ahmed", "Mohamed", "Mahmoud", "Sara", "Nour", "Mariam", "Omar", "Youssef", "Hana", "Karim",
         "Laila", "Ali", "Salma", "Hassan", "Dina", "Tamer", "Rana", "Khaled", "Farida", "Amr",
         "Yasmin", "Ibrahim", "Nada", "Mostafa", "Heba", "Tarek", "Jana", "Ziad", "Malak", "Adel"]
LAST = ["Hassan", "Ibrahim", "Mostafa", "Saleh", "Nabil", "Fathy", "Ezzat", "Gamal", "Soliman", "Farouk",
        "Abdelrahman", "Sherif", "Refaat", "Mansour", "Kamel", "Zaki", "Osman", "Lotfy", "Barakat", "Shaheen"]
REGIONS = ["Cairo", "Giza", "Alexandria", "Dakahlia", "Gharbia", "Sharqia", "Beheira", "Minya"]

COMMENTS_POS = ["Quick and helpful", "Agent was very polite", "Solved right away", "Great service"]
COMMENTS_NEG = ["Waited too long", "Had to call again", "Issue not resolved", "Agent could not help",
                "Transferred too many times"]
COMMENTS_NEU = ["It was okay", "Average experience"]


def daterange(a, b):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


# --------------------------------------------------------------------------------------
# 1. CLEAN (TRUE) DATA
# --------------------------------------------------------------------------------------
def demand_mult(tid, d):
    m = 1.0
    if d >= GROWTH_START:
        m *= 1.08
    if tid == 1 and d >= MIGRATION:
        m *= 1.25
    if tid == 5 and d >= COMPLAINT_SPIKE:
        m *= 1.30
    if tid == 3 and d >= GROWTH_START:
        m *= 1.05
    return m


def build_clean(R, NP):
    # ---- teams ----
    teams = [dict(team_id=t, team_name=T["name"], primary_channel=T["channel"], site=T["site"])
             for t, T in TEAMS.items()]

    # ---- agents ----
    names = set()
    while len(names) < 31:
        names.add(f"{R.choice(FIRST)} {R.choice(LAST)}")
    names = sorted(names)
    R.shuffle(names)
    off_patterns = [(4, 5), (4, 5), (4, 5), (5, 6), (3, 4), (6, 0), (0, 1)]
    agents, n = [], 0
    for tid, T in TEAMS.items():
        for i in range(T["headcount"]):
            n += 1
            agents.append(dict(
                agent_id=f"A{n:03d}", agent_name=names[n - 1], team_id=tid,
                hire_date=date(2022, 1, 1) + timedelta(days=R.randrange(0, 1400)),
                term=None, is_new=False, q=R.gauss(0, 1), speed=R.lognormvariate(0, 0.08),
                off=R.choice(off_patterns)))
        if tid == 2:
            for i in range(3):   # new-hire cohort
                n += 1
                agents.append(dict(
                    agent_id=f"A{n:03d}", agent_name=names[n - 1], team_id=tid,
                    hire_date=NEW_HIRE_START, term=None, is_new=True, q=R.gauss(-0.4, 1),
                    speed=R.lognormvariate(0, 0.08), off=R.choice(off_patterns)))
    billing = [a for a in agents if a["team_id"] == 1]
    billing[-1]["term"] = ATTRITION
    by_team = defaultdict(list)
    for a in agents:
        by_team[a["team_id"]].append(a)

    # ---- customers ----
    n_cust = 15000
    weights = NP.pareto(1.6, n_cust) + 1.0
    cumw = np.cumsum(weights / weights.sum())
    customers = []
    for i in range(n_cust):
        customers.append(dict(
            customer_id=f"C{i + 1:05d}",
            segment=R.choices(["Consumer", "SMB", "Enterprise"], [70, 22, 8])[0],
            region=R.choice(REGIONS),
            signup_date=date(2019, 1, 1) + timedelta(days=R.randrange(0, 2650))))

    interactions, surveys, shifts = [], [], []
    pending = defaultdict(list)
    qa_pool = defaultdict(list)
    seq = 0
    sur_seq = 0
    shift_seq = 0

    for d in daterange(START, END):
        # ---- shifts / availability ----
        avail = defaultdict(list)
        for a in agents:
            if a["hire_date"] > d or (a["term"] and a["term"] <= d):
                continue
            if d.weekday() in a["off"]:
                continue
            p_abs = 0.10 if (a["team_id"] == 1 and d >= MIGRATION) else 0.04
            absent = R.random() < p_abs
            shift_seq += 1
            if absent:
                logged, adherent = 0, 0
            else:
                logged = max(0, int(480 - abs(R.gauss(8, 8))))
                adherent = int(logged * min(max(R.gauss(0.92, 0.03), 0.75), 0.99))
            shifts.append(dict(shift_id=f"SH{shift_seq:06d}", agent_id=a["agent_id"], shift_date=d,
                               scheduled_minutes=480, logged_in_minutes=logged,
                               adherent_minutes=adherent, absent=absent,
                               updated_at=f"{d.isoformat()}T23:59:59"))
            if not absent:
                avail[a["team_id"]].append(a)

        # ---- contacts per team ----
        for tid, T in TEAMS.items():
            ch = T["channel"]
            active = [a for a in by_team[tid]
                      if a["hire_date"] <= d and not (a["term"] and a["term"] <= d)]
            pool = avail[tid] or active
            wf = {4: 0.6, 5: 0.8}.get(d.weekday(), 1.0)
            mean = T["demand"] * wf * demand_mult(tid, d) * R.lognormvariate(0, 0.05)
            n_new = int(NP.poisson(mean))

            cats = list(T["cats"].keys())
            cw = list(T["cats"].values())
            if d >= MIGRATION and tid in (3, 4):
                cw = [w * 1.6 if c == "Billing" else w for c, w in zip(cats, cw)]
            new_cats = R.choices(cats, cw, k=n_new)
            cust_idx = np.searchsorted(cumw, NP.random(n_new)).clip(0, n_cust - 1)
            contacts = [(int(ci), c) for ci, c in zip(cust_idx, new_cats)] + pending.pop((d, tid), [])
            load = len(contacts) / (len(pool) * T["cap"])
            mult = min(max(math.exp(3.0 * (load - 0.8)), 0.6), 6.0)

            for ci, cat in contacts:
                seq += 1
                hour = R.choices(HOURS[ch], cum_weights=CUMW[ch])[0]
                created = datetime(d.year, d.month, d.day, hour) + timedelta(seconds=R.randrange(3600))
                if ch == "Email":
                    wait = R.lognormvariate(math.log(WAIT_BASE[ch] * mult ** 0.6), 0.7)
                    abandoned = False
                else:
                    wait = R.expovariate(1.0 / (WAIT_BASE[ch] * mult))
                    patience = R.expovariate(1.0 / PATIENCE[ch])
                    abandoned = patience < wait
                pw = PRIORITY_W.get(cat, [50, 35, 15])
                row = dict(interaction_id=f"INT-{seq:07d}", customer_id=customers[ci]["customer_id"],
                           queue_id=tid, channel=ch, issue_category=cat,
                           priority=R.choices(["Low", "Medium", "High"], pw)[0],
                           created_at=created)
                if abandoned:
                    ended = created + timedelta(seconds=patience)
                    row.update(agent_id=None, agent_name=None, status="Abandoned", answered_at=None,
                               ended_at=ended, resolved_at=None, wait_seconds=round(patience),
                               handle_seconds=None, first_contact_resolved=None, escalated=False,
                               transferred=False, updated_at=iso(ended))
                    interactions.append(row)
                    if R.random() < 0.5:   # caller rings back
                        fd = d + timedelta(days=R.choice([1, 1, 2]))
                        if fd <= END:
                            pending[(fd, tid)].append((ci, cat))
                    continue

                a = R.choice(pool)
                weeks = max((d - a["hire_date"]).days, 0) / 7.0
                nh = math.exp(-weeks / 6.0) if a["is_new"] else 0.0
                med = HANDLE_MEDIAN[cat] * CH_HANDLE_MULT[ch] * a["speed"] * (1 + 0.35 * nh)
                if cat == "Billing" and d >= MIGRATION:
                    med *= 1.22
                handle = max(30.0, R.lognormvariate(math.log(med), 0.40))

                p_fcr = FCR_BASE[cat] + CH_FCR_ADJ[ch] + 0.03 * a["q"] - 0.12 * nh
                if cat == "Billing" and d >= MIGRATION:
                    p_fcr -= 0.15
                if load > 1:
                    p_fcr -= 0.05 * (load - 1)
                fcr = R.random() < min(max(p_fcr, 0.2), 0.97)

                p_esc = (0.03 + (0.12 if cat == "Complaint" else 0) + (0.05 if cat == "Technical" else 0)
                         + (0.08 if not fcr else 0) + 0.03 * nh)
                if cat == "Billing" and d >= MIGRATION:
                    p_esc *= 1.4
                escalated = R.random() < min(p_esc, 0.6)
                transferred = R.random() < (0.04 + 0.05 * nh + (0.03 if not fcr else 0))

                answered = created + timedelta(seconds=wait)
                ended = answered + timedelta(seconds=handle)
                if fcr:
                    resolved = ended
                else:
                    resolved = ended + timedelta(hours=R.lognormvariate(math.log(30), 0.8))
                    if R.random() < 0.03 or resolved > END_DT:
                        resolved = None
                if resolved:
                    status = "Resolved"
                elif escalated:
                    status = "Escalated"
                else:
                    status = R.choice(["Open", "Pending"])

                row.update(agent_id=a["agent_id"], agent_name=a["agent_name"], status=status,
                           answered_at=answered, ended_at=ended, resolved_at=resolved,
                           wait_seconds=round(wait), handle_seconds=round(handle),
                           first_contact_resolved=fcr, escalated=escalated, transferred=transferred,
                           updated_at=iso(resolved or ended))
                interactions.append(row)
                qa_pool[(a["agent_id"], d.isocalendar()[:2])].append((row, a, nh))

                if not fcr and R.random() < 0.5:   # repeat contact
                    fd = d + timedelta(days=R.choice([1, 2, 2, 3, 4]))
                    if fd <= END:
                        pending[(fd, tid)].append((ci, cat))

                # ---- survey ----
                wait_pen = (0.15 * min(wait / 14400, 2)) if ch == "Email" else 0.5 * min(wait / 120, 3)
                latent = (4.25 + 0.30 * a["q"] - (0 if fcr else 0.85) - wait_pen
                          - (0.5 if escalated else 0) - (0.2 if transferred else 0)
                          - (0.3 if handle > 1.8 * med else 0) + R.gauss(0, 0.75))
                if R.random() < 0.24 + (0.10 if latent < 3 else 0):
                    csat = int(min(max(round(latent), 1), 5))
                    ces = int(min(max(round(csat * 1.3 + R.gauss(0, 0.8)), 1), 7))
                    comment = None
                    if R.random() < 0.35:
                        comment = R.choice(COMMENTS_NEG if csat <= 2 else COMMENTS_POS if csat >= 4 else COMMENTS_NEU)
                    sub = min(ended + timedelta(hours=R.uniform(1, 48)), END_DT)
                    sur_seq += 1
                    surveys.append(dict(survey_id=f"SUR-{sur_seq:07d}", interaction_id=row["interaction_id"],
                                        csat_score=csat, ces_score=ces, comment=comment,
                                        submitted_at=sub, updated_at=iso(sub)))

    # ---- QA evaluations: 3 sampled interactions per agent per week ----
    qa, qa_seq = [], 0
    evaluators = ["Nadia Farouk", "Hossam Reda", "Rania Salem"]
    for (agent_id, _wk), items in sorted(qa_pool.items()):
        for row, a, nh in R.sample(items, min(3, len(items))):
            score = 84 + 5 * a["q"] + R.gauss(0, 5) - 8 * nh
            if row["issue_category"] == "Billing" and row["created_at"].date() >= MIGRATION:
                score -= 3
            ev = min(row["ended_at"] + timedelta(days=R.randint(1, 5)), END_DT)
            qa_seq += 1
            qa.append(dict(qa_id=f"QA-{qa_seq:06d}", interaction_id=row["interaction_id"], agent_id=agent_id,
                           evaluator=R.choice(evaluators), evaluated_at=ev,
                           qa_score=round(min(max(score, 40), 100), 1), updated_at=iso(ev)))

    interactions.sort(key=lambda r: r["created_at"])
    return teams, agents, customers, interactions, surveys, qa, shifts


# --------------------------------------------------------------------------------------
# 2. MESSY (RAW) LAYER
# --------------------------------------------------------------------------------------
CH_VAR = {"Voice": ["voice", "VOICE", "Phone", "phone call", "Call"],
          "Chat": ["chat", "Live Chat", "LIVE CHAT", "web chat"],
          "Email": ["email", "E-mail", "EMAIL", "e-mail"]}
ST_VAR = {"Resolved": ["resolved", "RESOLVED", "Closed", "closed", "Solved"],
          "Pending": ["pending", "Pending Customer", "PENDING", "In Progress"],
          "Open": ["open", "OPEN", "New"],
          "Abandoned": ["abandoned", "Abandon", "ABANDONED", "Dropped"],
          "Escalated": ["escalated", "ESCALATED", "Tier 2"]}
CAT_VAR = {"Billing": ["billing", "Billing & Payments", "billing issue", "Biling"],
           "Technical": ["technical", "Tech Support", "Technical Issue", "TECHNICAL"],
           "Account Access": ["account access", "Account Acces", "Login/Account", "Account"],
           "Delivery/Order": ["Delivery", "delivery / order", "Order Status", "Delivery/order"],
           "Complaint": ["complaint", "Complaints", "COMPLAINT"],
           "Product Inquiry": ["product inquiry", "Product Enquiry", "Product Info"],
           "Cancellation": ["cancellation", "Cancel Service", "CANCELLATION"]}


class Messer:
    def __init__(self, R):
        self.R = R
        self.log = Counter()

    def ts(self, dt, tag):
        if dt is None:
            return None
        r = self.R.random()
        if r < 0.90:
            return iso(dt)
        if r < 0.96:
            self.log[f"{tag}: dd/mm/YYYY HH:MM:SS format"] += 1
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        if r < 0.985:
            self.log[f"{tag}: 'Mon DD, YYYY HH:MM AM' format"] += 1
            return dt.strftime("%b %d, %Y %I:%M %p")
        if r < 0.995:
            self.log[f"{tag}: epoch seconds"] += 1
            return calendar.timegm(dt.timetuple())
        self.log[f"{tag}: date only (time lost)"] += 1
        return dt.strftime("%Y-%m-%d")

    def boolean(self, v, tag):
        if v is None:
            return None
        r = self.R.random()
        if r < 0.005:
            self.log[f"{tag}: null"] += 1
            return None
        if r < 0.70:
            return bool(v)
        self.log[f"{tag}: non-boolean encoding (Y/N, 1/0, yes/no, TRUE/FALSE)"] += 1
        if r < 0.80:
            return "Y" if v else "N"
        if r < 0.90:
            return 1 if v else 0
        if r < 0.95:
            return "yes" if v else "no"
        return "TRUE" if v else "FALSE"

    def name(self, nm):
        if nm is None:
            return None
        if self.R.random() > 0.22:
            return nm
        self.log["agent_name: inconsistent formatting/typo"] += 1
        first, last = nm.split(" ", 1)
        k = self.R.randrange(7)
        if k == 0:
            return nm.lower()
        if k == 1:
            return nm.upper()
        if k == 2:
            return f"{last}, {first}"
        if k == 3:
            return f"{first}  {last}"
        if k == 4:
            return nm + " "
        if k == 5:
            i = self.R.randrange(1, len(nm) - 2)
            return nm[:i] + nm[i + 1] + nm[i] + nm[i + 2:]
        return f"{first[0]}. {last}"

    def variant(self, value, table, p, tag):
        if self.R.random() < p:
            self.log[f"{tag}: inconsistent text"] += 1
            return self.R.choice(table[value])
        return value


def dup_rows(rows, R, log, tag, exact_p, near_p=0.0, id_key=None, near_fn=None):
    out = []
    for r in rows:
        out.append(r)
        if R.random() < exact_p:
            out.append(dict(r))
            log[f"{tag}: exact duplicate rows"] += 1
        if near_p and R.random() < near_p:
            out.append(near_fn(r))
            log[f"{tag}: near-duplicate rows (new id, same event)"] += 1
    return out


def mess_interactions(rows, R, M):
    out = []
    ids = {a["agent_id"] for a in rows if a["agent_id"]}
    cats = list(CAT_VAR)
    for r in rows:
        m = dict(r)
        for f in ("created_at", "answered_at", "ended_at", "resolved_at"):
            m[f] = M.ts(r[f], f)
        if r["answered_at"] and R.random() < 0.01:
            m["answered_at"] = None
            M.log["answered_at: missing"] += 1
        if r["ended_at"] and R.random() < 0.01:
            m["ended_at"] = None
            M.log["ended_at: missing"] += 1
        if r["ended_at"] and R.random() < 0.003:
            m["ended_at"] = iso(r["created_at"] - timedelta(minutes=R.randint(1, 90)))
            M.log["ended_at: earlier than created_at (invalid)"] += 1

        x = R.random()
        if x < 0.02:
            m["customer_id"] = R.choice([None, "", "NULL"])
            M.log["customer_id: null/empty"] += 1
        elif x < 0.05:
            m["customer_id"] = R.choice([r["customer_id"].lower(), " " + r["customer_id"]])
            M.log["customer_id: inconsistent formatting"] += 1

        m["channel"] = M.variant(r["channel"], CH_VAR, 0.25, "channel")
        m["status"] = M.variant(r["status"], ST_VAR, 0.30, "status")
        if R.random() < 0.007:
            m["issue_category"] = M.variant(R.choice([c for c in cats if c != r["issue_category"]]),
                                            {c: [c] for c in cats}, 1, "issue_category(wrong)")
            M.log["issue_category: wrong category (undetectable by rule)"] += 1
        else:
            m["issue_category"] = M.variant(r["issue_category"], CAT_VAR, 0.12, "issue_category")

        if r["agent_id"]:
            if R.random() < 0.06:
                m["agent_id"] = None
                M.log["agent_id: null (only agent_name present)"] += 1
            m["agent_name"] = M.name(r["agent_name"])
        for f in ("first_contact_resolved", "escalated", "transferred"):
            m[f] = M.boolean(r[f], f)

        if r["handle_seconds"] is not None:
            x = R.random()
            h = r["handle_seconds"]
            if x < 0.002:
                m["handle_seconds"] = -abs(h)
                M.log["handle_seconds: negative"] += 1
            elif x < 0.005:
                m["handle_seconds"] = 0
                M.log["handle_seconds: zero"] += 1
            elif x < 0.0065:
                m["handle_seconds"] = h * 50
                M.log["handle_seconds: extreme outlier"] += 1
            elif x < 0.0075:
                m["handle_seconds"] = "N/A"
                M.log["handle_seconds: text 'N/A'"] += 1
            elif x < 0.0095:
                m["handle_seconds"] = f"{h}s"
                M.log["handle_seconds: text with unit suffix"] += 1
        x = R.random()
        if x < 0.001:
            m["wait_seconds"] = -r["wait_seconds"]
            M.log["wait_seconds: negative"] += 1
        elif x < 0.002:
            m["wait_seconds"] = r["wait_seconds"] * 100
            M.log["wait_seconds: extreme outlier"] += 1

        x = R.random()
        if x < 0.03:
            m["priority"] = None
            M.log["priority: null"] += 1
        elif x < 0.10:
            m["priority"] = R.choice([r["priority"].lower(), r["priority"].upper()])
            M.log["priority: inconsistent text"] += 1
        out.append(m)

    def near(r):
        n = dict(r)
        n["interaction_id"] = r["interaction_id"].replace("INT-", "INT-9")
        return n

    return dup_rows(out, R, M.log, "interactions", 0.015, 0.008, near_fn=near)


def mess_surveys(rows, R, M):
    out = []
    for r in rows:
        m = dict(r)
        m["submitted_at"] = M.ts(r["submitted_at"], "survey.submitted_at")
        x = R.random()
        if x < 0.005:
            m["csat_score"] = R.choice([0, 6, 9, 10])
            M.log["csat_score: out of range (valid is 1-5)"] += 1
        elif x < 0.009:
            m["csat_score"] = "N/A"
            M.log["csat_score: text 'N/A'"] += 1
        elif x < 0.012:
            m["csat_score"] = f"{r['csat_score']}/5"
            M.log["csat_score: text like '4/5'"] += 1
        out.append(m)
    return dup_rows(out, R, M.log, "surveys", 0.01)


def mess_qa(rows, R, M):
    out = []
    for r in rows:
        m = dict(r)
        m["evaluated_at"] = M.ts(r["evaluated_at"], "qa.evaluated_at")
        x = R.random()
        if x < 0.01:
            m["qa_score"] = round(r["qa_score"] / 100, 3)
            M.log["qa_score: 0-1 scale instead of 0-100"] += 1
        elif x < 0.013:
            m["qa_score"] = round(r["qa_score"] + 30, 1)
            M.log["qa_score: above 100 (invalid)"] += 1
        if R.random() < 0.10:
            m["evaluator"] = R.choice([r["evaluator"].lower(), r["evaluator"].upper()])
            M.log["evaluator: inconsistent text"] += 1
        out.append(m)
    return dup_rows(out, R, M.log, "qa_evaluations", 0.01)


def mess_shifts(rows, R, M):
    out = []
    for r in rows:
        m = dict(r)
        m["shift_date"] = r["shift_date"].isoformat()
        if R.random() < 0.04:
            m["shift_date"] = r["shift_date"].strftime("%d-%m-%Y")
            M.log["shift_date: dd-mm-YYYY format"] += 1
        if R.random() < 0.004:
            m["logged_in_minutes"] = None
            M.log["logged_in_minutes: null"] += 1
        out.append(m)
    return dup_rows(out, R, M.log, "shifts", 0.005)


def mess_customers(rows, R, M):
    out = []
    for r in rows:
        m = dict(r)
        m["signup_date"] = r["signup_date"].isoformat()
        if R.random() < 0.05:
            m["signup_date"] = r["signup_date"].strftime("%d/%m/%Y")
            M.log["signup_date: dd/mm/YYYY format"] += 1
        x = R.random()
        if x < 0.02:
            m["segment"] = None
            M.log["segment: null"] += 1
        elif x < 0.20:
            m["segment"] = R.choice([r["segment"].lower(), r["segment"].upper(), r["segment"] + " "])
            M.log["segment: inconsistent text"] += 1
        if R.random() < 0.03:
            m["region"] = None
            M.log["region: null"] += 1
        m["updated_at"] = "2026-03-31T00:00:00"
        out.append(m)
    return dup_rows(out, R, M.log, "customers", 0.005)


# --------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    R = random.Random(args.seed)
    NP = np.random.default_rng(args.seed)

    print("Generating clean synthetic data ...")
    teams, agents, customers, inter, surveys, qa, shifts = build_clean(R, NP)

    raw_dir = Path("data/raw")
    key_dir = Path("answer_key")
    raw_dir.mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)

    # truth file (clean interactions)
    fields = list(inter[0].keys())
    with gzip.open(key_dir / "truth_interactions.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted(set().union(*[r.keys() for r in inter[:2000]])))
        w.writeheader()
        for r in inter:
            w.writerow({k: (iso(v) if isinstance(v, datetime) else v) for k, v in r.items()})

    print("Injecting defects ...")
    M = Messer(R)
    agents_out = [dict(agent_id=a["agent_id"], agent_name=a["agent_name"], team_id=a["team_id"],
                       hire_date=a["hire_date"].isoformat(),
                       termination_date=a["term"].isoformat() if a["term"] else None,
                       status="Inactive" if a["term"] else "Active") for a in agents]
    tables = {
        "teams": teams,
        "agents": agents_out,
        "customers": mess_customers(customers, R, M),
        "interactions": mess_interactions(inter, R, M),
        "surveys": mess_surveys(surveys, R, M),
        "qa_evaluations": mess_qa(qa, R, M),
        "shifts": mess_shifts(shifts, R, M),
    }
    for name, rows in tables.items():
        with open(raw_dir / f"{name}.json", "w") as f:
            json.dump(rows, f)
        print(f"  {name:15s} {len(rows):>8,} rows")

    with open(key_dir / "defect_log.json", "w") as f:
        json.dump(dict(sorted(M.log.items())), f, indent=2)
    print(f"\nDone. Raw files in {raw_dir}/  (answer key in {key_dir}/ -- don't peek yet!)")


if __name__ == "__main__":
    main()
