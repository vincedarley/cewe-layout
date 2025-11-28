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

import copy
import random
from typing import List, Tuple, Optional

from .base import LayoutAlgorithm


class TreeNode:
    """Node in a binary slicing tree.
    
    Internal nodes (I nodes) have a cut direction ('V' or 'H').
    Leaf nodes (L nodes) reference a photo/rectangle.
    """
    
    def __init__(self, label=None, is_leaf=False, photo_idx=None):
        self.label = label  # 'V', 'H' for internal nodes, or photo index for leaves
        self.is_leaf = is_leaf
        self.photo_idx = photo_idx  # Index into rectangles list (for leaf nodes)
        self.left = None
        self.right = None
        self.parent = None
        
        # Computed during layout
        self.aspect_ratio = None  # Width/height ratio
        self.width = None
        self.height = None
        self.x = None
        self.y = None
    
    def count_leaves(self):
        """Count leaf nodes in this subtree."""
        if self.is_leaf:
            return 1
        left_count = self.left.count_leaves() if self.left else 0
        right_count = self.right.count_leaves() if self.right else 0
        return left_count + right_count
    
    def collect_subtrees(self, min_leaves=3):
        """Collect all subtrees with at least min_leaves leaf nodes."""
        subtrees = []
        leaf_count = self.count_leaves()
        if not self.is_leaf and leaf_count >= min_leaves:
            subtrees.append(self)
        if self.left:
            subtrees.extend(self.left.collect_subtrees(min_leaves))
        if self.right:
            subtrees.extend(self.right.collect_subtrees(min_leaves))
        return subtrees


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
        return TreeNode(label=photo_indices[0], is_leaf=True, photo_idx=photo_indices[0])
    
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
                          photo_idx=shuffled_indices[leaf_idx])
            leaf.parent = node
            node.left = leaf
            leaf_idx += 1
        if node.right is None:
            leaf = TreeNode(label=shuffled_indices[leaf_idx], is_leaf=True,
                          photo_idx=shuffled_indices[leaf_idx])
            leaf.parent = node
            node.right = leaf
            leaf_idx += 1
    
    return root


def _compute_aspect_ratios(node: TreeNode, rectangles) -> float:
    """Compute aspect ratio recursively (Lemma 1).
    
    Args:
        node: Tree node
        rectangles: List of LayoutRectangle objects
        
    Returns:
        Aspect ratio (width/height) of this subtree
    """
    if node.is_leaf:
        rect = rectangles[node.photo_idx]
        node.aspect_ratio = rect.width / rect.height if rect.height > 0 else 1.0
        return node.aspect_ratio
    
    # Recursively compute children
    a1 = _compute_aspect_ratios(node.left, rectangles)
    a2 = _compute_aspect_ratios(node.right, rectangles)
    
    # Apply Lemma 1
    if node.label == 'V':
        # Vertical cut: aspect ratios add
        node.aspect_ratio = a1 + a2
    else:  # 'H'
        # Horizontal cut: reciprocal formula
        node.aspect_ratio = (a1 * a2) / (a1 + a2)
    
    return node.aspect_ratio


def _compute_dimensions(node: TreeNode, width: float, height: float, rectangles):
    """Compute dimensions recursively (Lemma 2).
    
    Args:
        node: Tree node
        width: Available width
        height: Available height
        rectangles: List of LayoutRectangle objects
    """
    if node.is_leaf:
        # Lemma 2: largest image that fits in canvas
        rect = rectangles[node.photo_idx]
        aspect = rect.width / rect.height if rect.height > 0 else 1.0
        node.width = min(width, aspect * height)
        node.height = node.width / aspect
        return
    
    # Allocate space to children based on aspect ratios
    a1 = node.left.aspect_ratio
    a2 = node.right.aspect_ratio
    
    if node.label == 'V':
        # Vertical cut: divide width
        # Both children get full height
        w1 = width * (a1 / (a1 + a2))
        w2 = width * (a2 / (a1 + a2))
        _compute_dimensions(node.left, w1, height, rectangles)
        _compute_dimensions(node.right, w2, height, rectangles)
        # Set this node's dimensions
        node.width = node.left.width + node.right.width
        node.height = height
    else:  # 'H'
        # Horizontal cut: divide height
        # Both children get full width
        h1 = height * (a2 / (a1 + a2))
        h2 = height * (a1 / (a1 + a2))
        _compute_dimensions(node.left, width, h1, rectangles)
        _compute_dimensions(node.right, width, h2, rectangles)
        # Set this node's dimensions
        node.width = width
        node.height = node.left.height + node.right.height


def _compute_layout(node: TreeNode, x: float, y: float):
    """Compute positions recursively.
    
    Args:
        node: Tree node
        x: X position of this subtree
        y: Y position of this subtree
    """
    node.x = x
    node.y = y
    
    if node.is_leaf:
        return
    
    if node.label == 'V':
        # Vertical cut: left child at (x,y), right child to the right
        _compute_layout(node.left, x, y)
        _compute_layout(node.right, x + node.left.width, y)
    else:  # 'H'
        # Horizontal cut: left child at (x,y), right child below
        _compute_layout(node.left, x, y)
        _compute_layout(node.right, x, y + node.left.height)


def _evaluate_cost(tree: TreeNode, canvas_width: float, canvas_height: float,
                  rectangles, lambda_param: float = 0.5) -> float:
    """Evaluate cost function (Section III.C).
    
    Cost = λ * size_error + (1-λ) * (1 - coverage)
    
    Args:
        tree: Layout tree
        canvas_width: Canvas width
        canvas_height: Canvas height
        rectangles: List of LayoutRectangle objects
        lambda_param: Trade-off parameter (default 0.5)
        
    Returns:
        Cost value (lower is better)
    """
    canvas_area = canvas_width * canvas_height
    
    # Collect all leaf nodes
    leaves = []
    def collect_leaves(node):
        if node.is_leaf:
            leaves.append(node)
        else:
            if node.left:
                collect_leaves(node.left)
            if node.right:
                collect_leaves(node.right)
    collect_leaves(tree)
    
    # Compute normalized desired sizes
    total_desired = sum(rect.preferred_size for rect in rectangles)
    desired_normalized = [rect.preferred_size / total_desired for rect in rectangles]
    
    # Compute size error term
    size_error = 0.0
    for leaf in leaves:
        actual_area = leaf.width * leaf.height
        actual_normalized = actual_area / canvas_area
        desired = desired_normalized[leaf.photo_idx]
        
        # Piecewise error function
        if actual_normalized < desired:
            k = 0.5
        else:
            k = 1.0
        
        size_error += k * abs(actual_normalized - desired)
    
    # Compute coverage term
    total_photo_area = sum(leaf.width * leaf.height for leaf in leaves)
    coverage = total_photo_area / canvas_area
    
    # Combined cost
    cost = lambda_param * size_error + (1 - lambda_param) * (1 - coverage)
    
    return cost


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
        node1.photo_idx, node2.photo_idx = node2.photo_idx, node1.photo_idx
    
    return tree


def _crossover_trees(tree1: TreeNode, tree2: TreeNode) -> Tuple[TreeNode, TreeNode]:
    """Crossover operator: swap subtree structures while preserving leaf labels.
    
    Per Fan (2012): "the labels of the leaf nodes remain in the original tree
    and are assigned to new I nodes." This means we swap the internal node
    structure (topology) but keep each tree's original photo assignments.
    
    Args:
        tree1: First parent tree
        tree2: Second parent tree
        
    Returns:
        Tuple of two offspring trees
    """
    # Deep copy to avoid modifying parents
    offspring1 = copy.deepcopy(tree1)
    offspring2 = copy.deepcopy(tree2)
    
    # Find all subtrees with >= 3 leaves (excluding the root to avoid issues)
    subtrees1 = [st for st in offspring1.collect_subtrees(min_leaves=3) if st.parent is not None]
    subtrees2 = [st for st in offspring2.collect_subtrees(min_leaves=3) if st.parent is not None]
    
    if not subtrees1 or not subtrees2:
        return offspring1, offspring2
    
    # Find pairs with matching leaf counts
    pairs = []
    for st1 in subtrees1:
        count1 = st1.count_leaves()
        for st2 in subtrees2:
            count2 = st2.count_leaves()
            if count1 == count2:
                pairs.append((st1, st2))
    
    if not pairs:
        return offspring1, offspring2
    
    # Randomly select a pair to crossover
    st1, st2 = random.choice(pairs)
    
    # Collect leaf labels from each subtree (to preserve them)
    def collect_leaf_labels(node):
        if node.is_leaf:
            return [node.photo_idx]
        labels = []
        if node.left:
            labels.extend(collect_leaf_labels(node.left))
        if node.right:
            labels.extend(collect_leaf_labels(node.right))
        return labels
    
    labels1 = collect_leaf_labels(st1)
    labels2 = collect_leaf_labels(st2)
    
    # Create deep copies of the subtrees to swap their structure
    st1_structure = copy.deepcopy(st1)
    st2_structure = copy.deepcopy(st2)
    
    # Reassign leaf labels: st1's structure gets st2's labels, st2's structure gets st1's labels
    def reassign_labels(node, labels, idx=[0]):
        if node.is_leaf:
            node.label = labels[idx[0]]
            node.photo_idx = labels[idx[0]]
            idx[0] += 1
        else:
            if node.left:
                reassign_labels(node.left, labels, idx)
            if node.right:
                reassign_labels(node.right, labels, idx)
    
    reassign_labels(st1_structure, labels2, [0])  # st1's structure gets st2's labels
    reassign_labels(st2_structure, labels1, [0])  # st2's structure gets st1's labels
    
    # Replace subtrees in offspring
    # st1_structure (with labels2) replaces st1 in offspring1
    # st2_structure (with labels1) replaces st2 in offspring2
    st1_structure.parent = st1.parent
    if st1.parent.left == st1:
        st1.parent.left = st1_structure
    else:
        st1.parent.right = st1_structure
    
    st2_structure.parent = st2.parent
    if st2.parent.left == st2:
        st2.parent.left = st2_structure
    else:
        st2.parent.right = st2_structure
    
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
                 lambda_param=0.5, elite_size=2):
        """
        Initialize Fan's layout algorithm.
        
        Args:
            population_size: Number of individuals in population
            generations: Number of generations to evolve
            mutation_rate: Probability of mutation
            crossover_rate: Probability of crossover
            lambda_param: Cost function trade-off (0=coverage, 1=size match)
            elite_size: Number of best individuals to preserve
        """
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.lambda_param = lambda_param
        self.elite_size = elite_size
    
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
            
            # Initialize population
            population = [_generate_random_tree(n_photos, photo_indices) 
                         for _ in range(self.population_size)]
            
            best_tree = None
            best_cost = float('inf')
            
            # Evolve population
            for generation in range(self.generations):
                # Evaluate all individuals
                fitness_scores = []
                for tree in population:
                    # Fast O(N) evaluation
                    _compute_aspect_ratios(tree, rectangles)
                    _compute_dimensions(tree, page_width, page_height, rectangles)
                    _compute_layout(tree, 0, 0)
                    
                    cost = _evaluate_cost(tree, page_width, page_height, 
                                        rectangles, self.lambda_param)
                    fitness_scores.append(cost)
                    
                    if cost < best_cost:
                        best_cost = cost
                        best_tree = copy.deepcopy(tree)
                
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
                        child1 = copy.deepcopy(parent1)
                        child2 = copy.deepcopy(parent2)
                    
                    # Mutation
                    if random.random() < self.mutation_rate:
                        child1 = _mutate_tree(child1)
                    if random.random() < self.mutation_rate:
                        child2 = _mutate_tree(child2)
                    
                    new_population.append(child1)
                    if len(new_population) < self.population_size:
                        new_population.append(child2)
                
                population = new_population
            
            # Validate that we found a valid tree
            if best_tree is None:
                return False, [], "Failed to generate valid layout tree"
            
            # Extract final layout from best tree
            _compute_aspect_ratios(best_tree, rectangles)
            _compute_dimensions(best_tree, page_width, page_height, rectangles)
            _compute_layout(best_tree, 0, 0)
            
            # Update rectangles in-place
            def update_rectangles(node):
                if node.is_leaf:
                    rect = rectangles[node.photo_idx]
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
