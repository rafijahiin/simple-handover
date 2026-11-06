"""
Fistula Campaign Q1 + Q2 archive — CIPRB's paper-era compilation.

These campaigns (Feb-May 2026) predate SIMPLE's daily digital reporting, so
they enter as FIXED, clearly-labelled archive figures (RCH request, confirmed
by Dr. Tanjina 17 Aug 2026: merge common AND extra upazilas, and drive the
campaign map by population covered). Source file: "Fistula_ Campaign_Q1 &
Q2.xlsx" (mixed date formats normalised; Lalmohon's blank union/session cells
kept blank and reported back to CIPRB).

Where an upazila also has live daily submissions (the May campaigns were
partially double-entered digitally), the archive figures WIN for that upazila
— CIPRB's compilation is the signed record for Q1/Q2. Live rows remain the
source for any upazila the archive does not cover (i.e. Q3 onward).
"""

CAMPAIGN_ARCHIVE = [
    dict(quarter='Q1', district='Khagrachari', upazila='Panchari', start='2026-02-22', end='2026-03-08',
         chw=40, unions=5, awareness=8, courtyard=10,
         households=6205, population=31025, suspected=11),
    dict(quarter='Q1', district='Sherpur', upazila='Jhenaigati', start='2026-02-22', end='2026-03-08',
         chw=51, unions=4, awareness=4, courtyard=2,
         households=10089, population=50445, suspected=5),
    dict(quarter='Q1', district='Sunamganj', upazila='Shantiganj', start='2026-02-18', end='2026-03-11',
         chw=75, unions=8, awareness=2, courtyard=13,
         households=9149, population=58683, suspected=7),
    dict(quarter='Q1', district='Bhola', upazila='Lalmohon', start='2026-02-24', end='2026-03-10',
         chw=85, unions=None, awareness=None, courtyard=None,
         households=2775, population=13875, suspected=1),
    dict(quarter='Q1', district='Kurigram', upazila='Ulipur', start='2026-02-22', end='2026-03-08',
         chw=165, unions=14, awareness=8, courtyard=15,
         households=45114, population=225570, suspected=6),
    dict(quarter='Q1', district='Sirajganj', upazila='Ullapara', start='2026-02-18', end='2026-03-05',
         chw=199, unions=14, awareness=82, courtyard=16,
         households=20386, population=81544, suspected=8),
    dict(quarter='Q1', district='Sirajganj', upazila='Tarash', start='2026-02-22', end='2026-03-08',
         chw=85, unions=8, awareness=28, courtyard=8,
         households=15220, population=60880, suspected=3),
    dict(quarter='Q1', district='Gaibandha', upazila='Saghata', start='2026-02-22', end='2026-03-08',
         chw=125, unions=10, awareness=102, courtyard=5,
         households=25982, population=129910, suspected=5),
    dict(quarter='Q1', district='Noakhali', upazila='Chatkhil', start='2026-02-24', end='2026-03-15',
         chw=66, unions=11, awareness=107, courtyard=4,
         households=22143, population=122050, suspected=4),
    dict(quarter='Q2', district='Khagrachari', upazila='Ramgarh', start='2026-05-06', end='2026-05-20',
         chw=39, unions=3, awareness=4, courtyard=5,
         households=5040, population=25200, suspected=3),
    dict(quarter='Q2', district='Khagrachari', upazila='Guimara', start='2026-05-06', end='2026-05-20',
         chw=31, unions=3, awareness=3, courtyard=3,
         households=4353, population=21765, suspected=2),
    dict(quarter='Q2', district='Sherpur', upazila='Jhenaigati', start='2026-05-05', end='2026-05-20',
         chw=41, unions=7, awareness=3, courtyard=3,
         households=3050, population=33930, suspected=3),
    dict(quarter='Q2', district='Sherpur', upazila='Nakla', start='2026-05-05', end='2026-05-20',
         chw=63, unions=13, awareness=4, courtyard=4,
         households=6300, population=46165, suspected=4),
    dict(quarter='Q2', district='Sunamganj', upazila='Dowarabazar', start='2026-05-07', end='2026-05-21',
         chw=51, unions=9, awareness=2, courtyard=4,
         households=7401, population=37005, suspected=4),
    dict(quarter='Q2', district='Sunamganj', upazila='Chhatak', start='2026-05-07', end='2026-05-21',
         chw=138, unions=13, awareness=3, courtyard=3,
         households=7671, population=38355, suspected=3),
    dict(quarter='Q2', district='Bhola', upazila='Char Fasson', start='2026-05-06', end='2026-05-20',
         chw=107, unions=9, awareness=5, courtyard=4,
         households=43400, population=217000, suspected=9),
    dict(quarter='Q2', district='Kurigram', upazila='Chilmari', start='2026-05-05', end='2026-05-20',
         chw=67, unions=6, awareness=5, courtyard=8,
         households=11476, population=57380, suspected=4),
    dict(quarter='Q2', district='Kurigram', upazila='Roumari', start='2026-05-05', end='2026-05-20',
         chw=94, unions=6, awareness=5, courtyard=7,
         households=15820, population=79100, suspected=3),
    dict(quarter='Q2', district='Sirajganj', upazila='Tarash', start='2026-05-02', end='2026-05-20',
         chw=41, unions=8, awareness=4, courtyard=6,
         households=4305, population=21525, suspected=4),
    dict(quarter='Q2', district='Sirajganj', upazila='Shahzadpur', start='2026-05-02', end='2026-05-20',
         chw=36, unions=13, awareness=6, courtyard=7,
         households=65462, population=327310, suspected=6),
    dict(quarter='Q2', district='Gaibandha', upazila='Sadullahpur', start='2026-05-07', end='2026-05-21',
         chw=45, unions=4, awareness=2, courtyard=1,
         households=6950, population=34750, suspected=1),
    dict(quarter='Q2', district='Gaibandha', upazila='Saghatta', start='2026-05-07', end='2026-05-21',
         chw=46, unions=4, awareness=3, courtyard=1,
         households=7120, population=35600, suspected=1),
    dict(quarter='Q2', district='Noakhali', upazila='Begumganj', start='2026-05-07', end='2026-05-21',
         chw=15, unions=6, awareness=5, courtyard=5,
         households=5350, population=134004, suspected=3),
    dict(quarter='Q2', district='Chadpur', upazila='Hajiganj', start='2026-05-10', end='2026-05-24',
         chw=15, unions=6, awareness=5, courtyard=5,
         households=2300, population=60708, suspected=3),
]
