"""
PLACEHOLDER scores (hand-typed guesses, NOT real data).
Only used when the sidebar checkbox is ticked. Replace with real datasets:
  safety    -> police.uk crimes per 1,000 residents (ONS population)
  transport -> TfL PTAL / journey times
  flood     -> Environment Agency Flood Zones 2/3
"""
import pandas as pd

_DATA = {
    "E09000001": (85, 100, 40), "E09000002": (60, 65, 50), "E09000003": (75, 70, 85),
    "E09000004": (78, 60, 70),  "E09000005": (70, 75, 80), "E09000006": (80, 65, 85),
    "E09000007": (55, 95, 80),  "E09000008": (72, 70, 90), "E09000009": (68, 75, 85),
    "E09000010": (76, 65, 75),  "E09000011": (65, 80, 60), "E09000012": (50, 85, 85),
    "E09000013": (62, 90, 30),  "E09000014": (65, 80, 85), "E09000015": (82, 65, 90),
    "E09000016": (78, 60, 85),  "E09000017": (70, 70, 75), "E09000018": (66, 75, 65),
    "E09000019": (58, 90, 80),  "E09000020": (64, 85, 75), "E09000021": (80, 70, 40),
    "E09000022": (65, 80, 70),  "E09000023": (70, 85, 60), "E09000024": (75, 75, 75),
    "E09000025": (62, 85, 65),  "E09000026": (72, 70, 80), "E09000027": (85, 80, 35),
    "E09000028": (68, 85, 50),  "E09000029": (82, 75, 85), "E09000030": (60, 90, 70),
    "E09000031": (74, 75, 80),  "E09000032": (70, 85, 55), "E09000033": (45, 95, 60),
}


def placeholder_external_scores() -> pd.DataFrame:
    return pd.DataFrame.from_dict(_DATA, orient="index", columns=["safety", "transport", "flood"])