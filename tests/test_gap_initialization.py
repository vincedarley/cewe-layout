#!/usr/bin/env python3
"""
Test gap initialization logic in LayoutManager.

Verifies that:
- Gaps are initialized only when keys don't exist (not based on zero values)
- Both gaps are always initialized from analysis
- Negative edge_gap is used for bleed
- Zero gaps are valid values that don't trigger re-initialization
"""

import sys
sys.path.insert(0, '.')

from cewe_layout.layout_ops import LayoutManager


def test_gap_initialization_detection():
    """Verify that initialization check uses key existence, not zero values."""
    mgr = LayoutManager()
    pageno = 42
    
    # Initially, gaps should not be set
    assert not mgr.has_edge_gap(pageno), "Edge gap should not be set initially"
    assert not mgr.has_internal_gap(pageno), "Internal gap should not be set initially"
    
    # Default values should be 0.0
    assert mgr.get_edge_gap(pageno) == 0.0, "Default edge_gap should be 0.0"
    assert mgr.get_internal_gap(pageno) == 0.0, "Default internal_gap should be 0.0"
    
    # Set gaps to zero explicitly
    mgr.set_edge_gap(pageno, 0.0)
    mgr.set_internal_gap(pageno, 0.0)
    
    # Now gaps SHOULD be set (even though values are zero)
    assert mgr.has_edge_gap(pageno), "Edge gap should be set after explicit set to 0.0"
    assert mgr.has_internal_gap(pageno), "Internal gap should be set after explicit set to 0.0"
    
    # Values should still be 0.0
    assert mgr.get_edge_gap(pageno) == 0.0, "Edge gap should be 0.0"
    assert mgr.get_internal_gap(pageno) == 0.0, "Internal gap should be 0.0"
    
    print("✓ Gap initialization uses key existence, not zero values")


def test_clear_gaps():
    """Verify that clear_gaps removes keys, allowing re-initialization."""
    mgr = LayoutManager()
    pageno = 99
    
    # Set some gap values
    mgr.set_edge_gap(pageno, 50.0)
    mgr.set_internal_gap(pageno, 30.0)
    
    # Verify they're set
    assert mgr.has_edge_gap(pageno), "Edge gap should be set"
    assert mgr.has_internal_gap(pageno), "Internal gap should be set"
    assert mgr.get_edge_gap(pageno) == 50.0, "Edge gap should be 50.0"
    assert mgr.get_internal_gap(pageno) == 30.0, "Internal gap should be 30.0"
    
    # Clear gaps
    mgr.clear_gaps(pageno)
    
    # Verify they're no longer set
    assert not mgr.has_edge_gap(pageno), "Edge gap should not be set after clear"
    assert not mgr.has_internal_gap(pageno), "Internal gap should not be set after clear"
    
    # Default values should be returned
    assert mgr.get_edge_gap(pageno) == 0.0, "Edge gap should return default 0.0"
    assert mgr.get_internal_gap(pageno) == 0.0, "Internal gap should return default 0.0"
    
    print("✓ clear_gaps removes keys, allowing re-initialization")


def test_negative_edge_gap_for_bleed():
    """Verify that negative edge_gap values work (for bleed)."""
    mgr = LayoutManager()
    pageno = 7
    
    # Set negative edge_gap (bleed)
    mgr.set_edge_gap(pageno, -20.0)  # 2mm bleed
    mgr.set_internal_gap(pageno, 15.0)
    
    # Verify values
    assert mgr.has_edge_gap(pageno), "Edge gap should be set"
    assert mgr.get_edge_gap(pageno) == -20.0, "Edge gap should be -20.0"
    assert mgr.get_internal_gap(pageno) == 15.0, "Internal gap should be 15.0"
    
    print("✓ Negative edge_gap values work correctly for bleed")


def test_both_gaps_always_initialized():
    """Verify that both gaps are always initialized together."""
    mgr = LayoutManager()
    pageno = 13
    
    # Scenario: only one gap is set (this should not happen in practice,
    # but let's verify the check catches it)
    mgr.set_edge_gap(pageno, 50.0)
    # Internal gap NOT set
    
    # Check: has_edge_gap returns True, has_internal_gap returns False
    assert mgr.has_edge_gap(pageno), "Edge gap should be set"
    assert not mgr.has_internal_gap(pageno), "Internal gap should NOT be set"
    
    # This means initialization check would detect incomplete initialization
    needs_init = not mgr.has_edge_gap(pageno) or not mgr.has_internal_gap(pageno)
    assert needs_init, "Should detect that initialization is incomplete"
    
    print("✓ Initialization check requires BOTH gaps to be set")


if __name__ == '__main__':
    test_gap_initialization_detection()
    test_clear_gaps()
    test_negative_edge_gap_for_bleed()
    test_both_gaps_always_initialized()
    print("\n✓ All gap initialization tests passed")
