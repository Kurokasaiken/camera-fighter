"""Matcher live: confronta una sequenza di feature con i template."""

import json
import os

from dtw import dtw_distance


class Matcher:
    def __init__(self, template_dir: str = "templates"):
        self.templates = {}
        self.template_dir = template_dir
        self.load_all()

    def load_all(self):
        if not os.path.exists(self.template_dir):
            return
        for name in os.listdir(self.template_dir):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.template_dir, name)
            with open(path, encoding="utf-8") as f:
                template = json.load(f)
            technique = template.get("technique", name.replace(".json", ""))
            self.templates[technique] = template

    def match(self, live_sequence: list, window: int = None) -> dict:
        """Restituisce score per ogni template."""
        if not live_sequence:
            return {}

        if window is None:
            window = max(len(live_sequence) // 4, 2)

        results = {}
        for name, template in self.templates.items():
            template_frames = template.get("frames", [])
            feature_keys = template.get("feature_keys", [])
            feature_ranges = template.get("ranges", {})
            if not template_frames or not feature_keys:
                continue
            dist = dtw_distance(live_sequence, template_frames, feature_keys,
                                feature_ranges=feature_ranges, window=window)
            # converto distanza in score (piu basso = meglio)
            score = 1.0 / (1.0 + dist)
            results[name] = round(score, 3)

        return results

    def best(self, live_sequence: list, threshold: float = 0.3) -> tuple:
        """Restituisce (tecnica, score) o ('', 0) se nessuna supera threshold."""
        results = self.match(live_sequence)
        if not results:
            return "", 0.0
        best_name = max(results, key=results.get)
        best_score = results[best_name]
        if best_score >= threshold:
            return best_name, best_score
        return "", 0.0
