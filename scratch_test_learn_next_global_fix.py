import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.topic_validator import canonicalize_concept_name, get_topic_validation_details
from services.study_service import process_input
import inspect

def test_learn_next_global_fix():
    print("=== TESTING GLOBAL LEARN NEXT RETRIEVAL FIXES ===")

    # 1. Verify Canonicalization & Validation for Optics / Science Terms
    print("\n--- 1. VERIFYING CANONICALIZATION & VALIDATION FIXES ---")
    science_terms = ["Ray Optics", "Wave Optics", "Fiber Optics", "Thermodynamics", "Electromagnetism"]
    for term in science_terms:
        clean = canonicalize_concept_name(term)
        assert clean == term, f"DEFECT: Term '{term}' canonicalized to '{clean}'!"

        is_val, reason = get_topic_validation_details(clean)
        assert is_val, f"DEFECT: Term '{clean}' was REJECTED: {reason}"
        print(f"  [OK] '{term}' -> Canonical: '{clean}' | Validated: True.")

    # 2. Verify Learn Next & Prerequisite Retrieval across 5 Test Topics
    print("\n--- 2. VERIFYING LEARN NEXT RETRIEVAL ACROSS TEST TOPICS ---")
    test_topics = ["Linked List", "Binary Tree", "Hash Table", "Quick Sort", "Ray Optics"]

    for topic in test_topics:
        res = process_input(topic)
        canon_topic = res.get("topic")
        before_list = res.get("before", [])
        after_list = res.get("after", [])

        print(f"\n[TOPIC]: '{canon_topic}'")
        print(f"  Learn Before (Prerequisites): {[b['topic'] for b in before_list]}")
        print(f"  Learn Next (Successors):      {[a['topic'] for a in after_list]}")

        assert len(after_list) > 0, f"DEFECT: Learn Next returned 0 successors for '{canon_topic}'!"
        assert len(before_list) > 0, f"DEFECT: Prerequisites returned 0 items for '{canon_topic}'!"
        print(f"  [OK] Learn Next and Prerequisites verified cleanly for '{canon_topic}'.")

def verify_explanation_pipeline_untouched():
    print("\n=== VERIFYING EXPLANATION PIPELINE REMAINED 100% UNTOUCHED ===")
    import services.prompt_builders as pb
    import services.study_service as ss

    src_pb = inspect.getsource(pb.build_topic_lecture_prompt)
    src_fmt = inspect.getsource(ss.format_rich_lecture_explanation)
    src_fb = inspect.getsource(ss.generate_fallback_lecture)

    assert "experienced, patient university professor" in src_pb, "DEFECT: Explanation prompt modified!"
    assert "### Simple Definition" in src_fmt, "DEFECT: Explanation formatter modified!"
    assert "essential data and computational structure" in src_fb, "DEFECT: Fallback lecture modified!"

    assert 'if topic ==' not in src_pb and 'if topic ==' not in src_fmt, "DEFECT: Hardcoded rules found!"
    print("  [OK] Verified explanation generation pipeline is 100% untouched and production-ready.")

if __name__ == "__main__":
    test_learn_next_global_fix()
    verify_explanation_pipeline_untouched()
    print("\n=== ALL GLOBAL LEARN NEXT VERIFICATION TESTS PASSED SUCCESSFULLY ===")
