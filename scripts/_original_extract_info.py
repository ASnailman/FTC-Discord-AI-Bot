"""Verbatim copy of the pre-fix extract_info (from src/rag_chain.py before
this hardening pass), kept only so scripts/eval_extraction.py --mode before
can measure a genuine baseline number against the same golden dataset,
rather than an estimate. Not used by the application.
"""
import re

STOP_WORDS = {"chances", "beating", "vs", "versus", 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k',
              'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'}


def extract_info_original(question: str, region_teams_dict: dict):
    teams_mentioned = set()

    valid_numbers = set(str(v) for v in region_teams_dict.values())
    found_numbers = re.findall(r'\b\d+\b', question)
    for num in found_numbers:
        if num in valid_numbers:
            teams_mentioned.add(int(num))

    clean_names_dict = {}
    for raw_name, number in region_teams_dict.items():
        clean_name = re.sub(r"['\-\._]", "", raw_name.lower())
        words = re.findall(r'\b[a-z0-9]+\b', clean_name)
        if words:
            joined_name = " ".join(words)
            if joined_name not in clean_names_dict:
                clean_names_dict[joined_name] = [int(number)]
            else:
                clean_names_dict[joined_name].append(int(number))

    clean_q = re.sub(r"['\-\._]", "", question.lower())
    q_words = re.findall(r'\b[a-z0-9]+\b', clean_q)

    used_indices = set()
    max_ngram_length = 5

    for n in range(max_ngram_length, 0, -1):
        for i in range(len(q_words) - n + 1):
            if any(idx in used_indices for idx in range(i, i + n)):
                continue
            ngram = " ".join(q_words[i:i + n])
            if ngram in clean_names_dict and ngram not in STOP_WORDS:
                for team_num in clean_names_dict[ngram]:
                    teams_mentioned.add(team_num)
                for idx in range(i, i + n):
                    used_indices.add(idx)

    return list(teams_mentioned)
