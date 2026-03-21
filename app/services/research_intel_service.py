"""
ResearchIntelService — quality scoring and niche playbook distillation.

Responsibilities:
  - score_research_run: compute edit-distance quality score on /approve and persist to ResearchRun
  - maybe_distill: consolidate raw telemetry into a NichePlaybook every 10 undistilled runs
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from difflib import SequenceMatcher

import httpx

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session

from ..models import NichePlaybook, ResearchRun
from ..settings import DEEPSEEK_API_KEY, DEEPSEEK_TIMEOUT

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


class ResearchIntelService:
    def __init__(self, db: Session):
        self.db = db

    def score_research_run(self, post_id: int, original: str, edited: str) -> None:
        """Compute edit-distance quality score and persist to the linked ResearchRun."""
        quality = round(SequenceMatcher(None, original.strip(), edited.strip()).ratio(), 3)
        run = self.db.query(ResearchRun).filter(ResearchRun.post_id == post_id).first()
        if run:
            run.quality_score = quality
            self.db.commit()

    async def maybe_distill(self, niche: str, profile_name: str) -> bool:
        """Consolidate undistilled runs into a NichePlaybook if >= 10 have accumulated."""
        undistilled_count = (
            self.db.query(ResearchRun)
            .filter(
                ResearchRun.profile_name == profile_name,
                ResearchRun.niche == niche,
                ResearchRun.is_distilled == False,
            )
            .count()
        )
        if undistilled_count < 10:
            return False

        runs = (
            self.db.query(ResearchRun)
            .filter(
                ResearchRun.profile_name == profile_name,
                ResearchRun.niche == niche,
                ResearchRun.is_distilled == False,
            )
            .all()
        )

        scored_runs = [r for r in runs if r.quality_score is not None]
        if len(scored_runs) >= 5:
            playbook = await self._distill_with_flash(niche, runs)
        else:
            playbook = self._compute_heuristic_playbook(runs)

        existing = (
            self.db.query(NichePlaybook)
            .filter(NichePlaybook.profile_name == profile_name, NichePlaybook.niche == niche)
            .first()
        )
        if existing:
            existing.playbook_json = json.dumps(playbook)
            existing.runs_distilled += len(runs)
            existing.version += 1
        else:
            self.db.add(NichePlaybook(
                profile_name=profile_name,
                niche=niche,
                playbook_json=json.dumps(playbook),
                runs_distilled=len(runs),
            ))

        for r in runs:
            r.is_distilled = True
        self.db.commit()
        return True

    def _compute_heuristic_playbook(self, runs: list) -> dict:
        """Pure stats aggregation — zero LLM cost."""
        tool_counter: Counter = Counter()
        kd_values: list[int] = []
        entity_counter: Counter = Counter()
        quality_scores: list[float] = []
        exa_patterns: list[str] = []

        for run in runs:
            try:
                tools = json.loads(run.tool_sequence_json or "[]")
                for t in tools:
                    tool_counter[t] += 1
            except Exception:
                pass
            if run.avg_kd is not None:
                kd_values.append(run.avg_kd)
            if run.max_kd_used is not None:
                kd_values.append(run.max_kd_used)
            try:
                entities = json.loads(run.entity_cluster_json or "[]")
                for e in entities:
                    entity_counter[e] += 1
            except Exception:
                pass
            if run.quality_score is not None:
                quality_scores.append(run.quality_score)
            try:
                exa_qs = json.loads(run.exa_queries_json or "[]")
                exa_patterns.extend(exa_qs[:2])
            except Exception:
                pass

        preferred_tools = [t for t, _ in tool_counter.most_common(6)]
        median_kd = int(sorted(kd_values)[len(kd_values) // 2]) if kd_values else 55
        min_kd = min(kd_values) if kd_values else 10

        return {
            "preferred_tool_sequence": preferred_tools,
            "kd_threshold": min(median_kd + 10, 65),
            "kd_sweet_spot": {"min": min_kd, "max": min(median_kd, 55)},
            "effective_exa_patterns": list(dict.fromkeys(exa_patterns))[:5],
            "recurring_info_gaps": [],
            "entity_clusters": [[e for e, _ in entity_counter.most_common(10)]],
            "tool_effectiveness": {t: round(c / len(runs), 2) for t, c in tool_counter.most_common(8)},
            "avg_quality_score": round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else None,
        }

    async def _distill_with_flash(self, niche: str, runs: list) -> dict:
        """Use DeepSeek V3 to distill run telemetry into a structured playbook (~$0.0001)."""
        run_summaries = []
        for run in runs[:20]:
            run_summaries.append({
                "keyword": run.keyword,
                "tools": json.loads(run.tool_sequence_json or "[]"),
                "iterations": run.iteration_count,
                "avg_kd": run.avg_kd,
                "max_kd": run.max_kd_used,
                "entities": json.loads(run.entity_cluster_json or "[]")[:8],
                "exa_queries": json.loads(run.exa_queries_json or "[]")[:3],
                "quality_score": run.quality_score,
            })

        prompt = (
            f"You are analyzing SEO research run data for the '{niche}' niche to produce a research playbook. "
            "Based on the following run telemetry, produce a JSON playbook with these exact keys:\n"
            "- preferred_tool_sequence: list of tool names in optimal order (most effective first)\n"
            "- kd_threshold: integer KD ceiling that worked best for this niche\n"
            "- kd_sweet_spot: object with 'min' and 'max' integer KD values\n"
            "- effective_exa_patterns: list of effective Exa search query patterns\n"
            "- recurring_info_gaps: list of 2-3 strings describing what competitors consistently miss\n"
            "- entity_clusters: list of lists of semantically related entity keywords\n"
            "- tool_effectiveness: object mapping tool name to effectiveness score 0.0-1.0\n"
            "- avg_quality_score: float average quality score across runs\n\n"
            "Return ONLY valid JSON, no markdown fences.\n\n"
            f"RUN DATA:\n{json.dumps(run_summaries, indent=2)[:6000]}"
        )

        try:
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You output valid JSON objects ONLY."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
            }

            async with httpx.AsyncClient(timeout=DEEPSEEK_TIMEOUT) as client:
                resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"].strip()

            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            return json.loads(text)
        except Exception as e:
            logger.error(f"[ResearchIntel] DeepSeek distillation failed: {e}. Using heuristic fallback.")
            return self._compute_heuristic_playbook(runs)
