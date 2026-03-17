"""
Domain Credibility Tier System

Replaces DataForSEO backlinks API with curated domain lists organized by industry.
4-tier scoring system: Tier 1 (40pts), Tier 2 (30pts), Tier 3 (20pts), Tier 4 (10pts), Unknown (0pts).

Organized by niche: cybersecurity, blueteam, redteam, purple team, GRC, technology, hacking, networking, AI.
"""

import logging

logger = logging.getLogger(__name__)

# ========================
# TIER 1: Authoritative Sources (40 points)
# ========================
# Government agencies, standards bodies, top academic institutions, peer-reviewed journals

TIER_1_DOMAINS = {
    # Government TLDs (wildcard matching)
    ".gov", ".mil", ".edu", ".ac.uk", "gov.uk", "gc.ca", "gov.au",

    # Cybersecurity Authorities
    "nist.gov",
    "cisa.gov",
    "us-cert.gov",
    "nvd.nist.gov",
    "owasp.org",
    "mitre.org",
    "cert.org",
    "sans.org",
    "first.org",
    "cve.mitre.org",
    "ics-cert.us-cert.gov",

    # GRC Standards Bodies
    "iso.org",
    "coso.org",
    "isaca.org",
    "iia.org.uk",

    # Data Protection Authorities
    "gdpr.eu",
    "ico.org.uk",
    "edps.europa.eu",
    "cnil.fr",

    # Networking Standards
    "ietf.org",
    "rfc-editor.org",
    "w3.org",
    "ieee.org",

    # Hacking Authorities
    "exploit-db.com",
    "cve.org",

    # Top Academic Institutions
    "mit.edu",
    "stanford.edu",
    "cmu.edu",
    "berkeley.edu",
    "oxford.ac.uk",
    "cambridge.org",
    "harvard.edu",
    "caltech.edu",
    "ethz.ch",
    "imperial.ac.uk",

    # Peer-Reviewed Journals
    "nature.com",
    "science.org",
    "cell.com",
    "acm.org",
    "ieee.org",
    "usenix.org",
    "pnas.org",
    "scientificamerican.com",
}

# ========================
# TIER 2: Industry Leaders (30 points)
# ========================
# Major security vendors, tech giants, consulting firms, leading AI labs

TIER_2_DOMAINS = {
    # Cybersecurity Vendors (Blue Team)
    "crowdstrike.com",
    "sentinelone.com",
    "paloaltonetworks.com",
    "checkpoint.com",
    "fortinet.com",
    "cisco.com",
    "splunk.com",
    "elastic.co",
    "rapid7.com",
    "tenable.com",
    "qualys.com",
    "cyberark.com",
    "okta.com",
    "mandiant.com",
    "fireeye.com",
    "trendmicro.com",
    "sophos.com",
    "mcafee.com",
    "symantec.com",
    "carbonblack.com",

    # Purple Team / Security Testing
    "attackiq.com",
    "safebreach.com",
    "verodin.com",

    # Cloud & Tech Giants
    "aws.amazon.com",
    "cloud.google.com",
    "azure.microsoft.com",
    "microsoft.com",
    "google.com",
    "ibm.com",
    "oracle.com",
    "redhat.com",
    "vmware.com",

    # AI/ML Leaders
    "openai.com",
    "anthropic.com",
    "deepmind.com",
    "huggingface.co",
    "arxiv.org",
    "hai.stanford.edu",
    "openreview.net",
    "kaggle.com",
    "papers.nips.cc",
    "neurips.cc",
    "meta.com",
    "ai.meta.com",
    "engineering.fb.com",
    "stability.ai",
    "cohere.com",
    "mistral.ai",
    "pytorch.org",
    "tensorflow.org",
    "blog.google",

    # GRC Consulting Firms
    "deloitte.com",
    "pwc.com",
    "ey.com",
    "kpmg.com",
    "gartner.com",
    "forrester.com",
    "idc.com",

    # Privacy & Compliance Organizations
    "iapp.org",
    "privacyinternational.org",
    "eff.org",

    # Bug Bounty Platforms
    "hackerone.com",
    "bugcrowd.com",
    "yeswehack.com",
    "intigriti.com",
    "synack.com",

    # Purple Team / Simulation
    "scythe.io",
    "redcanary.com",

    # Open Source Security Tools
    "wazuh.com",

    # Networking Vendors
    "juniper.net",
    "arista.com",
    "aruba.com",
    "extreme.com",
}

# ========================
# TIER 3: Expert Publications (20 points)
# ========================
# Industry publications, expert blogs, reputable tech media, academic publishers

TIER_3_DOMAINS = {
    # Cybersecurity Expert Blogs
    "krebsonsecurity.com",
    "schneier.com",
    "troyhunt.com",
    "danielmiessler.com",
    "grahamcluley.com",

    # Cybersecurity Publications
    "darkreading.com",
    "securityweek.com",
    "bleepingcomputer.com",
    "thehackernews.com",
    "threatpost.com",
    "cyberscoop.com",
    "scmagazine.com",
    "infosecurity-magazine.com",
    "securityintelligence.com",
    "csoonline.com",

    # Red Team / Offensive Security
    "pentestpartners.com",
    "bishopfox.com",
    "portswigger.net",
    "offensive-security.com",
    "hacking.land",
    "pentesterlab.com",
    "hackthebox.eu",
    "hackthebox.com",
    "tryhackme.com",
    "infosecwriteups.com",
    "book.hacktricks.xyz",
    "swarm.ptsecurity.com",

    # Blue Team / Detection
    "detection.fyi",
    "sigma-hq.io",
    "car.mitre.org",

    # AI/ML Publications
    "distill.pub",
    "technologyreview.com",
    "aiweirdness.com",
    "machinelearningmastery.com",

    # Compliance & Privacy Publications
    "complianceweek.com",
    "lawfaremedia.org",

    # Open Source Security Tools
    "zeek.org",
    "suricata.io",
    "osquery.io",

    # Networking
    "opennetworking.org",

    # Quality Tech Media
    "arstechnica.com",
    "wired.com",
    "hbr.org",
    "slashdot.org",
    "theregister.com",
    "zdnet.com",

    # Academic Publishers
    "springer.com",
    "elsevier.com",
    "sciencedirect.com",
    "wiley.com",
    "tandfonline.com",
    "sage.com",
}

# ========================
# TIER 4: General Tech Publishers (10 points)
# ========================
# General tech news, major business news outlets

TIER_4_DOMAINS = {
    # General Tech News
    "techcrunch.com",
    "theverge.com",
    "cnet.com",
    "venturebeat.com",
    "engadget.com",
    "gizmodo.com",
    "mashable.com",

    # Major Business/News Outlets
    "nytimes.com",
    "wsj.com",
    "reuters.com",
    "bloomberg.com",
    "economist.com",
    "forbes.com",
    "fortune.com",
    "businessinsider.com",
    "cnbc.com",
    "ft.com",
}


def normalize_domain(domain: str) -> str:
    """
    Normalize domain for matching.

    - Remove 'www.' prefix
    - Convert to lowercase
    - Strip whitespace
    """
    domain = domain.strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def get_domain_tier_score(domain: str) -> tuple[int, int]:
    """
    Get credibility tier and score for a domain.

    Returns:
        tuple[int, int]: (tier_level, score_points)
        - tier_level: 1-4 (or 0 for unknown)
        - score_points: 40, 30, 20, 10 (or 0 for unknown)

    Matching Logic:
        - Exact match: "nist.gov" matches "nist.gov"
        - Subdomain match: "nvd.nist.gov" matches "nist.gov"
        - TLD wildcard: "anything.gov" matches ".gov"

    Examples:
        >>> get_domain_tier_score("nist.gov")
        (1, 40)
        >>> get_domain_tier_score("nvd.nist.gov")
        (1, 40)
        >>> get_domain_tier_score("crowdstrike.com")
        (2, 30)
        >>> get_domain_tier_score("krebsonsecurity.com")
        (3, 20)
        >>> get_domain_tier_score("techcrunch.com")
        (4, 10)
        >>> get_domain_tier_score("random-blog.com")
        (0, 0)
    """
    domain = normalize_domain(domain)

    # Check each tier in order (1 -> 4)
    tiers = [
        (1, 40, TIER_1_DOMAINS),
        (2, 30, TIER_2_DOMAINS),
        (3, 20, TIER_3_DOMAINS),
        (4, 10, TIER_4_DOMAINS),
    ]

    for tier_level, score, tier_set in tiers:
        # Exact match
        if domain in tier_set:
            return (tier_level, score)

        # Subdomain match: "nvd.nist.gov" matches "nist.gov"
        for trusted_domain in tier_set:
            if not trusted_domain.startswith("."):  # Not a TLD wildcard
                if domain.endswith("." + trusted_domain):
                    return (tier_level, score)

        # TLD wildcard match: "anything.gov" matches ".gov"
        for tld_pattern in tier_set:
            if tld_pattern.startswith("."):  # TLD wildcard
                if domain.endswith(tld_pattern):
                    return (tier_level, score)

    # Unknown domain
    return (0, 0)


if __name__ == "__main__":
    # Quick test
    test_domains = [
        "nist.gov",
        "nvd.nist.gov",
        "crowdstrike.com",
        "krebsonsecurity.com",
        "techcrunch.com",
        "random-blog.com",
        "www.mit.edu",
        "security.nist.gov",
    ]

    print("Domain Tier Testing:")
    print("-" * 60)
    for domain in test_domains:
        tier, score = get_domain_tier_score(domain)
        print(f"{domain:30} → Tier {tier} (Score: {score})")
