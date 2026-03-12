from datetime import datetime
from sqlalchemy.orm import Session
from ..models import WriterRun, WriterPlaybook, Post
import json


class WriterIntelService:
    """Manages writer learning loop: capture, recall, reinforce, distill."""

    @staticmethod
    def score_writer_run(post_id: int, db: Session):
        """
        Score readability efficiency on approval.
        Formula: (10.0 - ari_score) / 10.0
        Higher score = closer to 7th-grade target.
        """
        writer_run = db.query(WriterRun).filter(WriterRun.post_id == post_id).first()
        if not writer_run:
            return  # No telemetry captured for this post

        # Compute efficiency: how close to optimal readability
        # ARI 7.5 target → efficiency = (10.0 - 7.5) / 10.0 = 0.25 (25% efficiency)
        # Lower ARI = higher efficiency
        efficiency = max(0.0, (10.0 - writer_run.ari_score) / 10.0)

        writer_run.readability_efficiency = efficiency
        writer_run.human_approved = True
        writer_run.approved_at = datetime.utcnow()
        db.commit()

    @staticmethod
    def maybe_distill(profile_name: str, niche: str, db: Session):
        """
        Distill writer playbook when ≥10 approved runs exist.
        Triggered after approval.
        """
        # Count undistilled runs with quality scores
        undistilled_runs = db.query(WriterRun).filter(
            WriterRun.profile_name == profile_name,
            WriterRun.niche == niche,
            WriterRun.is_distilled == False,
            WriterRun.readability_efficiency.isnot(None)
        ).all()

        if len(undistilled_runs) < 10:
            return  # Need ≥10 runs to distill

        # Only distill high-quality runs (efficiency ≥ 0.20)
        quality_runs = [r for r in undistilled_runs if r.readability_efficiency >= 0.20]

        if len(quality_runs) < 5:
            return  # Need ≥5 quality runs

        # Compute heuristic playbook (no LLM cost for MVP)
        playbook_data = WriterIntelService._compute_heuristic_playbook(quality_runs, db)

        # Upsert playbook
        existing = db.query(WriterPlaybook).filter(
            WriterPlaybook.profile_name == profile_name,
            WriterPlaybook.niche == niche
        ).first()

        if existing:
            existing.playbook_json = json.dumps(playbook_data)
            existing.runs_distilled += len(quality_runs)
            existing.version += 1
            existing.updated_at = datetime.utcnow()
        else:
            playbook = WriterPlaybook(
                profile_name=profile_name,
                niche=niche,
                playbook_json=json.dumps(playbook_data),
                runs_distilled=len(quality_runs)
            )
            db.add(playbook)

        # Mark runs as distilled
        for run in quality_runs:
            run.is_distilled = True

        db.commit()
        print(f"[WriterIntel] Distilled playbook for {profile_name}/{niche}: {len(quality_runs)} runs, version {existing.version + 1 if existing else 1}")

    @staticmethod
    def _compute_heuristic_playbook(runs: list, db: Session):
        """Compute playbook from run statistics (zero LLM cost)."""
        ari_scores = [r.ari_score for r in runs]
        avg_ari = sum(ari_scores) / len(ari_scores)

        efficiencies = [r.readability_efficiency for r in runs]
        avg_efficiency = sum(efficiencies) / len(efficiencies)

        sentence_lengths = [r.avg_sentence_length for r in runs]
        avg_sentence_length = sum(sentence_lengths) / len(sentence_lengths)

        return {
            "avg_ari_baseline": round(avg_ari, 2),
            "avg_readability_efficiency": round(avg_efficiency, 3),
            "effective_sentence_patterns": [],  # Populated in future LLM distillation
            "preferred_word_swaps": {},         # Populated in future LLM distillation
            "structure_template": {
                "target_avg_sentence_length": round(avg_sentence_length, 1),
                "h2_frequency_words": 180,      # Default from current system
                "list_blocks_per_article": 3    # Default from current system
            },
            "runs_distilled": len(runs),
            "version": 1
        }
