"""Check domain credibility cache status"""
from app.database import SessionLocal
from app.models import DomainCredibilityCache
from sqlalchemy import func

db = SessionLocal()

# Check cache statistics
total_entries = db.query(func.count(DomainCredibilityCache.id)).scalar()
print(f"\n[CACHE STATUS]")
print(f"Total cache entries: {total_entries}")

if total_entries > 0:
    print(f"\nSample cache entries:")
    print(f"{'Domain':<40} {'Niche':<20} {'Quality':<8} {'Integrity':<10} {'Checks':<7} {'Base Score'}")
    print("=" * 120)

    entries = db.query(DomainCredibilityCache).limit(20).all()
    for entry in entries:
        print(f"{entry.domain:<40} {entry.niche:<20} {entry.quality_score:<8.2f} {entry.integrity_score:<10.2f} {entry.check_count:<7} {entry.base_score:.1f}")

db.close()
