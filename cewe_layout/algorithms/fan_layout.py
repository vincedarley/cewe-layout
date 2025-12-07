"""
Jian Fan's photo layout algorithm (2012).

This module implements the genetic algorithm-based photo layout approach
described in:
    Fan, Jian. "Photo layout with a fast evaluation method and genetic algorithm."
    2012 IEEE International Conference on Multimedia and Expo Workshops. IEEE, 2012.

Key innovations:
- O(N) fast layout solver using slicing trees
- Fitness function balancing canvas coverage and size distribution
- Tree-based genetic operators (crossover and mutation)

Attribution:
    Based on the algorithm by Jian Fan (2012 ICMEW).
    Adapted for cewe-layout as a pluggable layout algorithm.
"""

import random
from typing import List, Tuple

from .base import LayoutAlgorithm, TreeNode
from .evaluator import evaluate_layout


def _generate_random_tree(n_photos: int, photo_indices: List[int]) -> TreeNode:
    """Generate a random binary slicing tree with N leaf nodes.
    
    Args:
        n_photos: Number of photos (leaf nodes)
        photo_indices: List of photo indices to assign to leaves
        
    Returns:
        Root node of the generated tree
    """
    if n_photos == 0:
        return None
    if n_photos == 1:
        return TreeNode(label=photo_indices[0], is_leaf=True, item_idx=photo_indices[0])
    
    # Step 1: Create internal nodes (N-1 for N leaves)
    n_internal = n_photos - 1
    internal_nodes = []
    
    # Create root
    root = TreeNode(label=random.choice(['V', 'H']), is_leaf=False)
    internal_nodes.append(root)
    
    # Step 2: Build tree structure by adding internal nodes
    for _ in range(n_internal - 1):
        # Select a random internal node with < 2 children
        candidates = [node for node in internal_nodes 
                     if (node.left is None or node.right is None)]
        parent = random.choice(candidates)
        
        # Create new internal node
        new_node = TreeNode(label=random.choice(['V', 'H']), is_leaf=False)
        new_node.parent = parent
        
        # Attach to parent
        if parent.left is None:
            parent.left = new_node
        else:
            parent.right = new_node
        
        internal_nodes.append(new_node)
    
    # Step 3: Fill remaining slots with leaf nodes
    shuffled_indices = photo_indices.copy()
    random.shuffle(shuffled_indices)
    leaf_idx = 0
    
    for node in internal_nodes:
        if node.left is None:
            leaf = TreeNode(label=shuffled_indices[leaf_idx], is_leaf=True, 
                          item_idx=shuffled_indices[leaf_idx])
            leaf.parent = node
            node.left = leaf
            leaf_idx += 1
        if node.right is None:
            leaf = TreeNode(label=shuffled_indices[leaf_idx], is_leaf=True,
                          item_idx=shuffled_indices[leaf_idx])
            leaf.parent = node
            node.right = leaf
            leaf_idx += 1
    
    return root




def _evaluate_cost(tree: TreeNode, canvas_width: float, canvas_height: float,
                  rectangles, size_importance: float = 100.0,
                  undersized_threshold: float = 0.5,
                  undersized_penalty: float = 5.0) -> float:
    """Evaluate cost function using centralized evaluator.
    
    This uses tree leaf nodes directly as LayoutRectangle-compatible objects
    by copying the necessary attributes from the original rectangles.
    
    Args:
        tree: Layout tree (with positioned leaf nodes)
        canvas_width: Canvas width
        canvas_height: Canvas height
        rectangles: List of LayoutRectangle objects (provides preferred_size)
        size_importance: Size importance parameter (λ, default 100.0)
        undersized_threshold: Ratio threshold for undersizing (default 0.5)
        undersized_penalty: Additional multiplier k for undersized photos (default 5.0)
        
    Returns:
        Cost value (lower is better)
    """
    # Collect leaf nodes from tree and copy LayoutRectangle attributes
    leaves = tree.collect_leaves()
    for node in leaves:
        # Copy LayoutRectangle-compatible attributes to the leaf node
        original_rect = rectangles[node.item_idx]
        node.item_id = original_rect.item_id
        node.preferred_size = original_rect.preferred_size
        node.preserve_aspect_ratio = original_rect.preserve_aspect_ratio
    
    # Use leaf nodes directly as LayoutRectangle-compatible objects
    return evaluate_layout(
        canvas_width, canvas_height, leaves,
        size_importance=size_importance,
        acceptable_empty_fraction=0.05,
        undersized_threshold=undersized_threshold,
        undersized_penalty=undersized_penalty,
        detailed=False
    )





def _mutate_tree(tree: TreeNode) -> TreeNode:
    """Mutation operator: swap labels of two random nodes of same type.
    
    Args:
        tree: Tree to mutate
        
    Returns:
        Mutated tree (modified in place)
    """
    # Collect all nodes by type
    internal_nodes = []
    leaf_nodes = []
    
    def collect_nodes(node):
        if node.is_leaf:
            leaf_nodes.append(node)
        else:
            internal_nodes.append(node)
            if node.left:
                collect_nodes(node.left)
            if node.right:
                collect_nodes(node.right)
    
    collect_nodes(tree)
    
    # Randomly choose to mutate internal or leaf nodes
    if random.random() < 0.5 and len(internal_nodes) >= 2:
        # Mutate internal nodes: swap V/H labels
        node1, node2 = random.sample(internal_nodes, 2)
        node1.label, node2.label = node2.label, node1.label
    elif len(leaf_nodes) >= 2:
        # Mutate leaf nodes: swap photo assignments
        node1, node2 = random.sample(leaf_nodes, 2)
        node1.label, node2.label = node2.label, node1.label
        node1.item_idx, node2.item_idx = node2.item_idx, node1.item_idx
    
    return tree


def _crossover_trees(tree1: TreeNode, tree2: TreeNode) -> Tuple[TreeNode, TreeNode]:
    """Crossover operator: swap subtree structures while swapping photo assignments.
    
    Algorithm:
    1. Find matching subtrees (same leaf count) from both parents
    2. Deep copy both subtrees
    3. Traverse both copies simultaneously and swap photo indices
    4. Replace: subtree1 (with parent2's photos) goes into parent2
                subtree2 (with parent1's photos) goes into parent1
    5. Skip if subtrees have identical structure (would be no-op)
    
    Args:
        tree1: First parent tree
        tree2: Second parent tree
        
    Returns:
        Tuple of two offspring trees
    """
    # Find candidate subtrees BEFORE copying (work on original trees)
    # Find all subtrees with >= 3 leaves (excluding the root to avoid issues)
    subtrees1 = [st for st in tree1.collect_subtrees(min_leaves=3) if st.parent is not None]
    subtrees2 = [st for st in tree2.collect_subtrees(min_leaves=3) if st.parent is not None]
    
    if not subtrees1 or not subtrees2:
        # No crossover possible - return clones
        return tree1.clone(), tree2.clone()
    
    # Find pairs with matching leaf counts
    pairs = []
    for st1 in subtrees1:
        count1 = st1.count_leaves()
        for st2 in subtrees2:
            count2 = st2.count_leaves()
            if count1 == count2:
                pairs.append((st1, st2))
    
    if not pairs:
        # No crossover possible - return clones
        return tree1.clone(), tree2.clone()
    
    # Randomly select a pair to crossover
    st1, st2 = random.choice(pairs)
    
    # Check if subtrees have identical structure (would be no-op)
    def trees_have_same_structure(node1, node2):
        """Check if two trees have identical branching structure."""
        if node1.is_leaf and node2.is_leaf:
            return True
        if node1.is_leaf != node2.is_leaf:
            return False
        if node1.label != node2.label:  # Different V/H split
            return False
        return (trees_have_same_structure(node1.left, node2.left) and 
                trees_have_same_structure(node1.right, node2.right))
    
    if trees_have_same_structure(st1, st2):
        # Identical structure - crossover would be no-op, try to find different pair
        valid_pairs = [(s1, s2) for s1, s2 in pairs if not trees_have_same_structure(s1, s2)]
        if not valid_pairs:
            # No valid crossover - return clones
            return tree1.clone(), tree2.clone()
        st1, st2 = random.choice(valid_pairs)
    
    # NOW clone entire trees (only when we know crossover will happen)
    offspring1 = tree1.clone()
    offspring2 = tree2.clone()
    
    # Find the corresponding subtrees in the offspring copies
    # We need to locate them by following the same path from root
    def find_subtree_in_copy(original_tree, original_subtree, copied_tree):
        """Find the corresponding subtree in a copied tree by matching path from root."""
        # Build path from root to subtree in original
        path = []
        node = original_subtree
        while node.parent is not None:
            parent = node.parent
            if parent.left == node:
                path.append('L')
            else:
                path.append('R')
            node = parent
        path.reverse()
        
        # Follow same path in copied tree
        node = copied_tree
        for direction in path:
            if direction == 'L':
                node = node.left
            else:
                node = node.right
        return node
    
    # Locate the subtrees in offspring copies
    st1_in_offspring1 = find_subtree_in_copy(tree1, st1, offspring1)
    st2_in_offspring2 = find_subtree_in_copy(tree2, st2, offspring2)
    
    # Clone ONLY the selected subtrees (these will be swapped)
    st1_copy = st1_in_offspring1.clone()
    st2_copy = st2_in_offspring2.clone()
    
    # Collect indices from both subtrees
    def collect_leaf_indices(node):
        """Collect photo indices from leaves in pre-order."""
        if node.is_leaf:
            return [node.item_idx]
        indices = []
        if node.left:
            indices.extend(collect_leaf_indices(node.left))
        if node.right:
            indices.extend(collect_leaf_indices(node.right))
        return indices
    
    indices1 = collect_leaf_indices(st1_copy)
    indices2 = collect_leaf_indices(st2_copy)
    
    # Reassign: st1_copy gets indices2, st2_copy gets indices1
    def reassign_indices(node, indices):
        """Reassign photo indices to leaves in pre-order."""
        idx = [0]
        def _reassign(n):
            if n.is_leaf:
                n.item_idx = indices[idx[0]]
                n.label = indices[idx[0]]
                idx[0] += 1
            else:
                if n.left:
                    _reassign(n.left)
                if n.right:
                    _reassign(n.right)
        _reassign(node)
    
    reassign_indices(st1_copy, indices2)  # st1 structure gets st2 photos
    reassign_indices(st2_copy, indices1)  # st2 structure gets st1 photos
    
    # Fix parent pointers
    def fix_parent_pointers(node, parent=None):
        node.parent = parent
        if node.left:
            fix_parent_pointers(node.left, node)
        if node.right:
            fix_parent_pointers(node.right, node)
    
    # Now: st1_copy has parent1's structure with parent2's photos
    #      st2_copy has parent2's structure with parent1's photos
    # Replace: st1_copy goes into offspring2 (parent2), st2_copy goes into offspring1 (parent1)
    
    fix_parent_pointers(st2_copy, st1_in_offspring1.parent)
    if st1_in_offspring1.parent.left == st1_in_offspring1:
        st1_in_offspring1.parent.left = st2_copy
    else:
        st1_in_offspring1.parent.right = st2_copy
    
    fix_parent_pointers(st1_copy, st2_in_offspring2.parent)
    if st2_in_offspring2.parent.left == st2_in_offspring2:
        st2_in_offspring2.parent.left = st1_copy
    else:
        st2_in_offspring2.parent.right = st1_copy
    
    return offspring1, offspring2


class FanLayoutAlgorithm(LayoutAlgorithm):
    """Jian Fan's genetic algorithm for photo layout (2012).
    
    Uses binary slicing trees with:
    - O(N) fast evaluation
    - Coverage + size distribution fitness
    - Tree-based crossover and mutation
    """
    
    def __init__(self, population_size=50, generations=100,
                 mutation_rate=0.2, crossover_rate=0.8,
                 size_importance=100.0, elite_size=2,
                 undersized_threshold=0.5, undersized_penalty=5.0):
        """
        Initialize Fan's layout algorithm.
        
        Args:
            population_size: Number of individuals in population
            generations: Number of generations to evolve
            mutation_rate: Probability of mutation
            crossover_rate: Probability of crossover
            size_importance: Size mismatch importance (λ parameter, default 100.0)
            elite_size: Number of best individuals to preserve
            undersized_threshold: Ratio threshold for undersizing (default 0.5)
            undersized_penalty: Additional multiplier k for undersized photos (default 5.0)
        """
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.size_importance = size_importance
        self.elite_size = elite_size
        self.undersized_threshold = undersized_threshold
        self.undersized_penalty = undersized_penalty
        
        # Store best tree from last run
        self.best_tree = None
    
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles,
        **kwargs
    ):
        """Generate layout using Fan's genetic algorithm.
        
        Args:
            page_width: Page width
            page_height: Page height
            rectangles: List of LayoutRectangle objects
            **kwargs: Additional parameters
            
        Returns:
            Tuple (success: bool, rects: list, error_msg: str)
        """
        try:
            if not rectangles:
                return False, [], "No rectangles to layout"
            
            # Validate input rectangles
            for i, rect in enumerate(rectangles):
                if rect.width <= 0 or rect.height <= 0:
                    return False, [], f"Invalid rectangle {i}: width={rect.width}, height={rect.height}"
            
            n_photos = len(rectangles)
            photo_indices = list(range(n_photos))
            
            # Initialize population with random trees
            population = [_generate_random_tree(n_photos, photo_indices) for _ in range(self.population_size)]
            
            best_tree = None
            best_cost = float('inf')
            
            # Evolve population
            for generation in range(self.generations):
                # Evaluate all individuals
                fitness_scores = []
                for tree in population:
                    # Fast O(N) evaluation using TreeNode methods
                    tree.compute_aspect_ratios(rectangles)
                    tree.compute_dimensions(page_width, page_height, rectangles)
                    tree.compute_layout(0, 0)
                    
                    cost = _evaluate_cost(tree, page_width, page_height, 
                                        rectangles, self.size_importance,
                                        self.undersized_threshold,
                                        self.undersized_penalty)
                    fitness_scores.append(cost)
                    
                    if cost < best_cost:
                        best_cost = cost
                        best_tree = tree.clone()
                
                # Selection: keep elite + tournament selection
                sorted_pop = sorted(zip(fitness_scores, population), 
                                  key=lambda x: x[0])
                elite = [tree for _, tree in sorted_pop[:self.elite_size]]
                
                # Create new population
                new_population = elite.copy()
                
                while len(new_population) < self.population_size:
                    # Tournament selection
                    tournament = random.sample(list(zip(fitness_scores, population)), 3)
                    parent1 = min(tournament, key=lambda x: x[0])[1]
                    tournament = random.sample(list(zip(fitness_scores, population)), 3)
                    parent2 = min(tournament, key=lambda x: x[0])[1]
                    
                    # Crossover
                    if random.random() < self.crossover_rate:
                        child1, child2 = _crossover_trees(parent1, parent2)
                    else:
                        # No crossover - delay deepcopy until needed
                        # Mutation will need copies, but if no mutation we can reuse parents
                        child1, child2 = parent1, parent2
                    
                    # Mutation - only deepcopy if we're going to mutate
                    if random.random() < self.mutation_rate:
                        # Need to clone before mutating (mutate modifies in place)
                        if child1 is parent1:  # Haven't cloned yet
                            child1 = parent1.clone()
                        child1 = _mutate_tree(child1)
                    else:
                        # No mutation - clone to avoid sharing references in population
                        if child1 is parent1:
                            child1 = parent1.clone()
                    
                    if random.random() < self.mutation_rate:
                        if child2 is parent2:
                            child2 = parent2.clone()
                        child2 = _mutate_tree(child2)
                    else:
                        if child2 is parent2:
                            child2 = parent2.clone()
                    
                    new_population.append(child1)
                    if len(new_population) < self.population_size:
                        new_population.append(child2)
                
                population = new_population
            
            # Validate that we found a valid tree
            if best_tree is None:
                return False, [], "Failed to generate valid layout tree"
            
            # Extract final layout from best tree
            best_tree.compute_aspect_ratios(rectangles)
            best_tree.compute_dimensions(page_width, page_height, rectangles)
            best_tree.compute_layout(0, 0)
            
            # Validate tree has all photos before updating
            def collect_photo_indices(node):
                if node.is_leaf:
                    return [node.item_idx]
                indices = []
                if node.left:
                    indices.extend(collect_photo_indices(node.left))
                if node.right:
                    indices.extend(collect_photo_indices(node.right))
                return indices
            
            photo_indices_in_tree = collect_photo_indices(best_tree)
            expected_indices = set(range(n_photos))
            actual_indices = set(photo_indices_in_tree)
            
            if actual_indices != expected_indices:
                missing = expected_indices - actual_indices
                extra = actual_indices - expected_indices
                return False, [], f"Tree corruption: missing photos {missing}, extra photos {extra}"
            
            # Store best tree for later retrieval
            self.best_tree = best_tree
            
            # Update rectangles in-place
            def update_rectangles(node):
                if node.is_leaf:
                    rect = rectangles[node.item_idx]
                    rect.x = node.x
                    rect.y = node.y
                    rect.width = node.width
                    rect.height = node.height
                    # Compute actual size based on layout dimensions
                    rect.actual_size = (rect.width * rect.height) / (page_width * page_height)
                else:
                    if node.left:
                        update_rectangles(node.left)
                    if node.right:
                        update_rectangles(node.right)
            
            update_rectangles(best_tree)
            
            # Validate all rectangles were positioned
            for i, rect in enumerate(rectangles):
                if rect.x is None or rect.y is None:
                    return False, [], f"Failed to position rectangle {i} (item_id={rect.item_id}). Tree structure issue."
            
            return True, rectangles, ""
        
        except Exception as e:
            return False, [], f"Layout generation error: {e}"
    
    def get_final_tree(self):
        """Return the final tree as a TreeNode for visualization/analysis.
        
        Returns:
            TreeNode representing the layout tree, or None if no layout generated yet.
        """
        return self.best_tree
