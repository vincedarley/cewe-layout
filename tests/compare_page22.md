# Page 22 Test vs GUI Comparison

## To investigate the discrepancy:

1. Run the test and save output:
   ```bash
   python tests/test_tree_cost.py 22 > /tmp/page22_test.txt 2>&1
   ```

2. Open GUI with debug enabled
   - Navigate to Page 22
   - Select "Tree Builder" algorithm
   - Enable "Debug Output" checkbox
   - Click "Generate Layout"
   - Copy the console output

3. Compare the outputs line by line:
   - Eval page dimensions (should be identical)
   - Edge/internal gaps (should be identical)
   - Number of rectangles (should be identical)
   - Each rectangle's preferred_size, dims, area (look for differences)
   - Total cost components

## Current Status:
- Test shows: cost=4736.79
- GUI shows: cost=6974.5
- Difference: ~47% higher in GUI

## Hypothesis:
Possible causes:
1. Different preferred_size calculation
2. Different rectangle dimensions from tree
3. Different evaluation parameters (size_importance, thresholds)
4. Different tree tolerance or build parameters

## Next Steps:
Once we see the GUI debug output, we can identify the exact difference.
