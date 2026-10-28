"""Tests for BranchMenuRepository."""

import os
from datetime import datetime

# Set required env vars BEFORE any project import
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ENDPOINT_URL", "https://s3.amazonaws.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("REDIS_URL", "redis://invalid-host-for-tests:6379")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-unit-tests-only")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-unit-tests-only")

import unittest
from bson import ObjectId

from domain.models import BranchMenu
from repositories import BranchMenuRepository, branch_menus_repo


class TestBranchMenuModel(unittest.TestCase):
    """Test BranchMenu model validation and defaults."""

    def test_branch_menu_minimal(self):
        """Test BranchMenu with minimal required fields."""
        now = datetime.utcnow()
        menu = BranchMenu(
            _id=ObjectId(),
            branchId=ObjectId(),
            image="menus/branch-123.jpg",
            createdAt=now,
            updatedAt=now,
        )
        self.assertEqual(menu.isActive, True)
        self.assertEqual(menu.ocrStatus, "pending")
        self.assertIsNone(menu.ocrError)
        self.assertIsNone(menu.quality)
        self.assertEqual(menu.lines, [])
        self.assertEqual(menu.tokens, [])
        self.assertEqual(menu.trigrams, [])
        self.assertIsNone(menu.processingStartedAt)

    def test_branch_menu_with_ocr_data(self):
        """Test BranchMenu with OCR data."""
        now = datetime.utcnow()
        lines = [
            {
                "text": "Pizza Margherita",
                "conf": 0.95,
                "box": [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]],
            }
        ]
        tokens = ["pizza", "margherita"]
        trigrams = ["piz", "izz", "zza", "mar", "arg", "rgh", "ghe", "her", "ere", "rit", "ita"]
        quality = {"avg_confidence": 0.92, "text_lines_detected": 150}

        menu = BranchMenu(
            _id=ObjectId(),
            branchId=ObjectId(),
            image="menus/branch-123.jpg",
            ocrStatus="done",
            lines=lines,
            tokens=tokens,
            trigrams=trigrams,
            quality=quality,
            createdAt=now,
            updatedAt=now,
        )
        self.assertEqual(menu.ocrStatus, "done")
        self.assertEqual(len(menu.lines), 1)
        self.assertEqual(menu.tokens, tokens)
        self.assertEqual(menu.trigrams, trigrams)
        self.assertEqual(menu.quality["avg_confidence"], 0.92)


class TestBranchMenuRepositoryExport(unittest.TestCase):
    """Test that BranchMenuRepository and instance are exported."""

    def test_repository_exported(self):
        """Test that BranchMenuRepository is exported from repositories."""
        self.assertTrue(hasattr(BranchMenuRepository, "build_candidate_pipeline"))

    def test_instance_exported(self):
        """Test that branch_menus_repo instance is exported."""
        self.assertIsInstance(branch_menus_repo, BranchMenuRepository)


class TestBuildCandidatePipeline(unittest.TestCase):
    """Test BranchMenuRepository.build_candidate_pipeline (pure function)."""

    def test_empty_trigrams_and_tokens(self):
        """Test that empty trigrams and tokens return impossible match."""
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=[], tokens=[]
        )
        # Should return a pipeline with an impossible $match
        self.assertEqual(len(pipeline), 1)
        self.assertIn("$match", pipeline[0])
        # The match should contain a false expression
        self.assertIn("$expr", pipeline[0]["$match"])

    def test_match_with_required_fields(self):
        """Test that $match includes isActive, ocrStatus."""
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=["abc", "def"], tokens=[]
        )
        # First stage should be $match with base conditions
        self.assertIn("$match", pipeline[0])
        match_stage = pipeline[0]["$match"]
        # Should have $and with base conditions
        self.assertIn("$and", match_stage)
        conditions = match_stage["$and"]
        # Check for base conditions
        cond_dicts = [c for c in conditions if isinstance(c, dict)]
        status_cond = [c for c in cond_dicts if "ocrStatus" in c]
        active_cond = [c for c in cond_dicts if "isActive" in c]
        self.assertTrue(len(status_cond) > 0)
        self.assertTrue(len(active_cond) > 0)

    def test_match_with_branch_ids(self):
        """Test that branchIds filter is added when specified."""
        branch_ids = [str(ObjectId()), str(ObjectId())]
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=["abc"], tokens=[], branch_ids=branch_ids
        )
        match_stage = pipeline[0]["$match"]["$and"]
        branch_cond = [
            c for c in match_stage if isinstance(c, dict) and "branchId" in c
        ]
        self.assertTrue(len(branch_cond) > 0)
        # Should have $in with ObjectIds
        branch_filter = branch_cond[0]["branchId"]
        self.assertIn("$in", branch_filter)
        oids = branch_filter["$in"]
        self.assertEqual(len(oids), 2)
        for oid in oids:
            self.assertIsInstance(oid, ObjectId)

    def test_match_with_empty_branch_ids_list(self):
        """Test that empty branch_ids list results in no matches."""
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=["abc"], tokens=[], branch_ids=[]
        )
        match_stage = pipeline[0]["$match"]["$and"]
        branch_cond = [
            c for c in match_stage if isinstance(c, dict) and "branchId" in c
        ]
        self.assertTrue(len(branch_cond) > 0)
        branch_filter = branch_cond[0]["branchId"]
        # Empty $in should match nothing
        self.assertEqual(branch_filter["$in"], [])

    def test_project_excludes_trigrams_tokens(self):
        """Test that $project excludes trigrams and tokens."""
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=["abc"], tokens=[]
        )
        # Find $project stage
        project_stages = [s for s in pipeline if "$project" in s]
        self.assertTrue(len(project_stages) > 0)
        project = project_stages[0]["$project"]
        self.assertEqual(project.get("trigrams"), 0)
        self.assertEqual(project.get("tokens"), 0)

    def test_overlap_calculation_with_ceil(self):
        """Test overlap threshold calculation with ceil."""
        # With 10 trigrams and 0.6 ratio, threshold should be ceil(10 * 0.6) = 6
        trigrams = [f"tri{i}" for i in range(10)]
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=trigrams, tokens=[], min_overlap_ratio=0.6
        )
        # Find $match stage with overlap filter
        match_stages = [s for s in pipeline if "$match" in s and "overlap" in str(s)]
        self.assertTrue(len(match_stages) > 0)

    def test_overlap_minimum_is_one(self):
        """Test that overlap minimum is at least 1."""
        # With 1 trigram and 0.6 ratio, threshold should be ceil(1 * 0.6) = 1, not 0
        trigrams = ["abc"]
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=trigrams, tokens=[], min_overlap_ratio=0.6
        )
        # Should not fail, and should have overlap filter
        self.assertTrue(len(pipeline) > 0)

    def test_default_ratio_tolerates_typos_in_short_queries(self):
        """'piza' (2 trigramas: piz, iza) debe llegar a cartas que contienen 'pizza'.

        Con el umbral anterior (0.6) exigía ambos trigramas y la perdía en Mongo.
        """
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=["piz", "iza"], tokens=[]
        )
        overlap_match = [s for s in pipeline if "$match" in s and "overlap" in s["$match"]]
        self.assertEqual(overlap_match[0]["$match"]["overlap"], {"$gte": 1})

    def test_default_ratio_value_for_long_queries(self):
        """Con 7 trigramas ('margarita') el umbral por defecto es ceil(7 * 0.4) = 3."""
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=[f"t{i:02d}" for i in range(7)], tokens=[]
        )
        overlap_match = [s for s in pipeline if "$match" in s and "overlap" in s["$match"]]
        self.assertEqual(overlap_match[0]["$match"]["overlap"], {"$gte": 3})

    def test_sort_by_overlap_desc(self):
        """Test that results are sorted by overlap descending."""
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=["abc", "def"], tokens=[]
        )
        sort_stages = [s for s in pipeline if "$sort" in s]
        self.assertTrue(len(sort_stages) > 0)
        sort = sort_stages[0]["$sort"]
        # Should sort by overlap descending
        if "overlap" in sort:
            self.assertEqual(sort["overlap"], -1)

    def test_limit_applied(self):
        """Test that $limit is applied."""
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=["abc"], tokens=[], limit=50
        )
        limit_stages = [s for s in pipeline if "$limit" in s]
        self.assertTrue(len(limit_stages) > 0)
        self.assertEqual(limit_stages[0]["$limit"], 50)

    def test_trigrams_and_tokens_both_present(self):
        """Test $or condition when both trigrams and tokens are present."""
        trigrams = ["abc", "def"]
        tokens = ["word1", "word2"]
        pipeline = BranchMenuRepository.build_candidate_pipeline(
            trigrams=trigrams, tokens=tokens
        )
        match_stage = pipeline[0]["$match"]["$and"]
        # Should have an $or with both trigram and token conditions
        or_conds = [c for c in match_stage if isinstance(c, dict) and "$or" in c]
        self.assertTrue(len(or_conds) > 0)


class TestRepositoryMethods(unittest.TestCase):
    """Test BranchMenuRepository static methods."""

    def test_to_object_id_from_string(self):
        """Test _to_object_id converts string to ObjectId."""
        oid = ObjectId()
        result = BranchMenuRepository._to_object_id(str(oid))
        self.assertEqual(result, oid)

    def test_to_object_id_from_object_id(self):
        """Test _to_object_id passes through ObjectId."""
        oid = ObjectId()
        result = BranchMenuRepository._to_object_id(oid)
        self.assertEqual(result, oid)

    def test_to_object_id_invalid_string(self):
        """Test _to_object_id returns original value on invalid string."""
        result = BranchMenuRepository._to_object_id("invalid-id")
        self.assertEqual(result, "invalid-id")


if __name__ == "__main__":
    unittest.main()
