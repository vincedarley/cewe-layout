#!/usr/bin/env python3
"""Compare Tree Builder vs Fan-GA results."""

tree_results = """
Page 10: cost=45.48, empty=1.30%, undersized=0
Page 11: cost=17.96, empty=1.13%, undersized=0
Page 12: cost=168.14, empty=0.01%, undersized=0
Page 13: cost=151.65, empty=1.15%, undersized=0
Page 14: cost=28.09, empty=1.25%, undersized=0
Page 15: cost=10.32, empty=0.96%, undersized=0
Page 16: cost=18.03, empty=1.11%, undersized=0
Page 17: cost=61.77, empty=1.57%, undersized=0
Page 18: cost=189.03, empty=3.40%, undersized=0
Page 19: cost=237.35, empty=1.52%, undersized=0
Page 2: cost=0.25, empty=0.10%, undersized=0
Page 20: cost=525.20, empty=1.44%, undersized=0
Page 22: cost=6974.49, empty=4.57%, undersized=0
Page 23: FAILED to build tree
Page 24: FAILED to build tree
Page 25: cost=126.73, empty=0.93%, undersized=0
Page 26: cost=112.37, empty=2.12%, undersized=0
Page 27: cost=145.20, empty=0.48%, undersized=0
Page 28: cost=224.49, empty=0.60%, undersized=0
Page 29: cost=88.96, empty=0.89%, undersized=0
Page 3: cost=138.35, empty=0.47%, undersized=0
Page 30: cost=8.50, empty=1.01%, undersized=0
Page 31: cost=90.43, empty=0.37%, undersized=0
Page 32: cost=7.21, empty=0.88%, undersized=0
Page 33: cost=326.26, empty=5.69%, undersized=0
Page 34: cost=13.00, empty=1.35%, undersized=0
Page 35: FAILED to build tree
Page 4: cost=447.56, empty=1.52%, undersized=0
Page 5: cost=148.17, empty=2.41%, undersized=0
Page 6: cost=158.16, empty=1.26%, undersized=0
Page 7: cost=171.80, empty=0.02%, undersized=0
Page 8: cost=260.29, empty=1.77%, undersized=0
Page 9: cost=513.74, empty=2.42%, undersized=0
""".strip().split('\n')

fanga_results = """
Page 10: cost=45.48, empty=1.30%, undersized=0
Page 11: cost=573277.13, empty=68.01%, undersized=6
Page 12: cost=0.49, empty=0.08%, undersized=0
Page 13: cost=501590.87, empty=9.37%, undersized=1
Page 14: cost=810758.23, empty=75.20%, undersized=8
Page 15: cost=134256.63, empty=10.48%, undersized=4
Page 16: cost=237557.31, empty=56.80%, undersized=5
Page 17: cost=71662.75, empty=6.52%, undersized=0
Page 18: cost=355240.82, empty=31.82%, undersized=4
Page 19: cost=332361.92, empty=63.18%, undersized=6
Page 2: cost=0.25, empty=0.10%, undersized=0
Page 20: cost=165878.14, empty=30.83%, undersized=4
Page 21: cost=529874.79, empty=41.51%, undersized=6
Page 22: cost=43107.27, empty=16.34%, undersized=0
Page 23: cost=380686.09, empty=71.35%, undersized=8
Page 24: cost=120855.31, empty=22.22%, undersized=6
Page 25: cost=59865.52, empty=2.11%, undersized=1
Page 26: cost=0.48, empty=0.14%, undersized=0
Page 27: cost=197371.94, empty=20.53%, undersized=3
Page 28: cost=69314.62, empty=10.96%, undersized=0
Page 29: cost=71717.29, empty=25.17%, undersized=0
Page 3: cost=165602.60, empty=47.31%, undersized=6
Page 30: cost=172311.15, empty=45.54%, undersized=6
Page 31: cost=214477.67, empty=57.73%, undersized=10
Page 32: cost=213567.83, empty=17.48%, undersized=5
Page 33: cost=112644.90, empty=12.34%, undersized=4
Page 34: cost=298581.69, empty=25.75%, undersized=13
Page 35: cost=63827.88, empty=12.59%, undersized=1
Page 4: cost=1038081.12, empty=77.43%, undersized=6
Page 5: cost=558181.37, empty=33.07%, undersized=1
Page 6: cost=158.16, empty=1.26%, undersized=0
Page 7: cost=0.29, empty=0.06%, undersized=0
Page 8: cost=144568.60, empty=33.55%, undersized=5
Page 9: cost=1044227.86, empty=26.64%, undersized=2
""".strip().split('\n')

# Parse results
def parse_line(line):
    parts = line.split(':')
    page_num = int(parts[0].replace('Page', '').strip())
    if 'FAILED' in line:
        return page_num, None, None, None
    cost_str = parts[1].split('cost=')[1].split(',')[0]
    empty_str = parts[1].split('empty=')[1].split('%')[0]
    under_str = parts[1].split('undersized=')[1].strip()
    return page_num, float(cost_str), float(empty_str), int(under_str)

tree_dict = {}
for line in tree_results:
    page, cost, empty, under = parse_line(line)
    tree_dict[page] = (cost, empty, under)

fanga_dict = {}
for line in fanga_results:
    page, cost, empty, under = parse_line(line)
    fanga_dict[page] = (cost, empty, under)

# Compare
print("="*80)
print("Tree Builder vs Fan-GA Comparison")
print("="*80)
print()

good_pages = []
bad_pages = []

for page in sorted(set(tree_dict.keys()) | set(fanga_dict.keys())):
    tree_cost, tree_empty, tree_under = tree_dict.get(page, (None, None, None))
    fanga_cost, fanga_empty, fanga_under = fanga_dict.get(page, (None, None, None))
    
    if tree_cost is None:
        print(f"Page {page:2d}: Tree=FAILED, Fan-GA={fanga_cost:.2f}")
        continue
    
    if fanga_cost is None:
        print(f"Page {page:2d}: Tree={tree_cost:.2f}, Fan-GA=FAILED")
        continue
    
    ratio = fanga_cost / tree_cost if tree_cost > 0 else float('inf')
    
    # Good if Fan-GA within 2x of Tree or both < 1.0
    is_good = (ratio < 2.0) or (fanga_cost < 1.0 and tree_cost < 200)
    
    status = "✓" if is_good else "✗"
    
    if is_good:
        good_pages.append(page)
    else:
        bad_pages.append(page)
    
    print(f"Page {page:2d} {status}: Tree={tree_cost:9.2f}, Fan-GA={fanga_cost:10.2f} (ratio={ratio:6.1f}x, empty={fanga_empty:5.2f}%, under={fanga_under})")

print()
print(f"Summary: {len(good_pages)} good, {len(bad_pages)} bad out of {len(tree_dict)} total")
print(f"Good pages: {good_pages}")
print(f"Bad pages: {bad_pages}")
