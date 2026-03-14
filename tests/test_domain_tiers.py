"""
Unit tests for domain tier scoring system.

Tests the get_domain_tier_score function with various domain patterns:
- Tier 1 government TLDs and authoritative sources
- Tier 2 industry leaders and major vendors
- Tier 3 expert publications and quality media
- Tier 4 general tech publishers
- Unknown domains
- Edge cases (www prefix, case sensitivity, subdomains)
"""

import pytest
from app.domain_tiers import get_domain_tier_score, normalize_domain


class TestNormalizeDomain:
    """Test domain normalization helper."""

    def test_removes_www_prefix(self):
        assert normalize_domain("www.example.com") == "example.com"

    def test_converts_to_lowercase(self):
        assert normalize_domain("EXAMPLE.COM") == "example.com"
        assert normalize_domain("Example.Com") == "example.com"

    def test_strips_whitespace(self):
        assert normalize_domain("  example.com  ") == "example.com"

    def test_combined_normalization(self):
        assert normalize_domain("  WWW.EXAMPLE.COM  ") == "example.com"


class TestTier1Domains:
    """Test Tier 1 (40 points) - Authoritative sources."""

    def test_government_exact_match(self):
        """Test exact match for government domains."""
        tier, score = get_domain_tier_score("nist.gov")
        assert tier == 1
        assert score == 40

    def test_government_subdomain(self):
        """Test subdomain matching for government."""
        tier, score = get_domain_tier_score("nvd.nist.gov")
        assert tier == 1
        assert score == 40

    def test_government_tld_wildcard(self):
        """Test TLD wildcard matching (.gov)."""
        tier, score = get_domain_tier_score("random.gov")
        assert tier == 1
        assert score == 40

    def test_edu_tld_wildcard(self):
        """Test .edu TLD wildcard."""
        tier, score = get_domain_tier_score("cs.random.edu")
        assert tier == 1
        assert score == 40

    def test_cybersecurity_authorities(self):
        """Test cybersecurity authoritative sources."""
        domains = ["cisa.gov", "owasp.org", "mitre.org", "cert.org", "sans.org"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 1, f"{domain} should be Tier 1"
            assert score == 40, f"{domain} should score 40"

    def test_academic_institutions(self):
        """Test top academic institutions."""
        domains = ["mit.edu", "stanford.edu", "cmu.edu", "berkeley.edu", "oxford.ac.uk"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 1, f"{domain} should be Tier 1"
            assert score == 40, f"{domain} should score 40"

    def test_peer_reviewed_journals(self):
        """Test peer-reviewed journals."""
        domains = ["nature.com", "science.org", "ieee.org", "acm.org"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 1, f"{domain} should be Tier 1"
            assert score == 40, f"{domain} should score 40"


class TestTier2Domains:
    """Test Tier 2 (30 points) - Industry leaders."""

    def test_cybersecurity_vendors(self):
        """Test major cybersecurity vendors."""
        domains = [
            "crowdstrike.com",
            "sentinelone.com",
            "paloaltonetworks.com",
            "splunk.com",
            "mandiant.com"
        ]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 2, f"{domain} should be Tier 2"
            assert score == 30, f"{domain} should score 30"

    def test_cloud_tech_giants(self):
        """Test cloud providers and tech giants."""
        domains = ["aws.amazon.com", "cloud.google.com", "azure.microsoft.com", "ibm.com"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 2, f"{domain} should be Tier 2"
            assert score == 30, f"{domain} should score 30"

    def test_ai_ml_leaders(self):
        """Test AI/ML leading organizations."""
        domains = ["openai.com", "anthropic.com", "deepmind.com", "huggingface.co", "arxiv.org"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 2, f"{domain} should be Tier 2"
            assert score == 30, f"{domain} should score 30"

    def test_grc_consulting_firms(self):
        """Test GRC consulting firms."""
        domains = ["deloitte.com", "pwc.com", "ey.com", "kpmg.com", "gartner.com"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 2, f"{domain} should be Tier 2"
            assert score == 30, f"{domain} should score 30"


class TestTier3Domains:
    """Test Tier 3 (20 points) - Expert publications."""

    def test_expert_blogs(self):
        """Test cybersecurity expert blogs."""
        domains = ["krebsonsecurity.com", "schneier.com", "troyhunt.com"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 3, f"{domain} should be Tier 3"
            assert score == 20, f"{domain} should score 20"

    def test_security_publications(self):
        """Test cybersecurity publications."""
        domains = [
            "darkreading.com",
            "securityweek.com",
            "bleepingcomputer.com",
            "thehackernews.com"
        ]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 3, f"{domain} should be Tier 3"
            assert score == 20, f"{domain} should score 20"

    def test_quality_tech_media(self):
        """Test quality tech media outlets."""
        domains = ["arstechnica.com", "wired.com", "hbr.org"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 3, f"{domain} should be Tier 3"
            assert score == 20, f"{domain} should score 20"

    def test_offensive_security(self):
        """Test red team / offensive security sources."""
        domains = ["portswigger.net", "offensive-security.com"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 3, f"{domain} should be Tier 3"
            assert score == 20, f"{domain} should score 20"


class TestTier4Domains:
    """Test Tier 4 (10 points) - General tech publishers."""

    def test_general_tech_news(self):
        """Test general tech news outlets."""
        domains = ["techcrunch.com", "theverge.com", "cnet.com", "venturebeat.com"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 4, f"{domain} should be Tier 4"
            assert score == 10, f"{domain} should score 10"

    def test_major_business_news(self):
        """Test major business/news outlets."""
        domains = ["nytimes.com", "wsj.com", "reuters.com", "bloomberg.com", "economist.com"]
        for domain in domains:
            tier, score = get_domain_tier_score(domain)
            assert tier == 4, f"{domain} should be Tier 4"
            assert score == 10, f"{domain} should score 10"


class TestUnknownDomains:
    """Test unknown domains (0 points)."""

    def test_random_blog(self):
        """Test unknown random blog."""
        tier, score = get_domain_tier_score("random-blog.com")
        assert tier == 0
        assert score == 0

    def test_unknown_tld(self):
        """Test unknown TLD."""
        tier, score = get_domain_tier_score("example.xyz")
        assert tier == 0
        assert score == 0

    def test_medium_blogs(self):
        """Test Medium blogs (not in tier lists)."""
        tier, score = get_domain_tier_score("medium.com")
        assert tier == 0
        assert score == 0


class TestEdgeCases:
    """Test edge cases and special patterns."""

    def test_www_prefix_removed(self):
        """Test that www prefix is handled correctly."""
        tier1, score1 = get_domain_tier_score("www.nist.gov")
        tier2, score2 = get_domain_tier_score("nist.gov")
        assert tier1 == tier2 == 1
        assert score1 == score2 == 40

    def test_case_insensitivity(self):
        """Test case-insensitive matching."""
        tier1, score1 = get_domain_tier_score("NIST.GOV")
        tier2, score2 = get_domain_tier_score("nist.gov")
        assert tier1 == tier2 == 1
        assert score1 == score2 == 40

    def test_subdomain_matching(self):
        """Test subdomain matching for tier domains."""
        # nvd.nist.gov should match nist.gov
        tier, score = get_domain_tier_score("nvd.nist.gov")
        assert tier == 1
        assert score == 40

        # blog.crowdstrike.com should match crowdstrike.com
        tier, score = get_domain_tier_score("blog.crowdstrike.com")
        assert tier == 2
        assert score == 30

    def test_tld_wildcard_priority(self):
        """Test that .gov TLD matches even for unknown subdomains."""
        tier, score = get_domain_tier_score("someagency.gov")
        assert tier == 1
        assert score == 40

    def test_academic_tld_combinations(self):
        """Test academic TLD patterns."""
        # .ac.uk pattern
        tier, score = get_domain_tier_score("someuniversity.ac.uk")
        assert tier == 1
        assert score == 40

        # .edu pattern
        tier, score = get_domain_tier_score("randomcollege.edu")
        assert tier == 1
        assert score == 40


class TestRealWorldScenarios:
    """Test real-world domain scenarios."""

    def test_security_blog_post_url(self):
        """Test domain extraction from typical blog post URL."""
        # In real usage, domain would be extracted from full URL
        # Here we test just the domain part
        tier, score = get_domain_tier_score("krebsonsecurity.com")
        assert tier == 3
        assert score == 20

    def test_government_agency_subdomain(self):
        """Test government subdomain like security.nist.gov."""
        tier, score = get_domain_tier_score("security.nist.gov")
        assert tier == 1
        assert score == 40

    def test_vendor_documentation_subdomain(self):
        """Test vendor docs subdomain like docs.splunk.com."""
        tier, score = get_domain_tier_score("docs.splunk.com")
        assert tier == 2
        assert score == 30
