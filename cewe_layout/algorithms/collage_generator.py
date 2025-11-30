"""
Collage-generator layout algorithm adapter.

This module wraps the collage-generator algorithm (based on Wu et al. 2016)
and adapts it to the cewe-layout LayoutAlgorithm interface.

Attribution:
    Original algorithm by Wu, Zhipeng, and Kiyoharu Aizawa.
    "Very fast generation of content-preserved photo collage under canvas size constraint."
    Multimedia Tools and Applications 75.4 (2016): 1813-1841.
    https://www.researchgate.net/publication/269455490_Very_fast_generation_of_content_preserved_photo_collage_under_canvas_size_constraint

    Adapted for cewe-layout as a pluggable layout algorithm.
@@
@@    Collage-generator reference implementation:
@@    https://github.com/n-gao/collage-generator
@@    © n-gao, licensed under MIT.
"""

import math
import random

import numpy as np

from .base import LayoutAlgorithm


class Node:
    """Tree node for collage layout representation."""
    
    def __init__(self, N, alpha_t=None, parent=None, split=None, rect=None, left=None, right=None):
        self.parent = parent
        self.left = left
        self.right = right
        self.split = split
        self.rect = rect
        self.N = N
        self.alpha_t = alpha_t

    @property
    def depth(self):
        if self.parent is None:
            return 0
        else:
            return self.parent.depth + 1

    @property
    def alpha(self):
        if self.rect is not None:
            return self.rect.width / self.rect.height if self.rect.height > 0 else 1.0
        alpha_left = self.left.alpha
        alpha_right = self.right.alpha
        if self.split == "V":
            return alpha_left + alpha_right
        else:
            return (alpha_left * alpha_right) / (alpha_left + alpha_right)


def _sample_energies(energies, temperature=1):
    """Sample an index from energies using Boltzmann distribution."""
    energies = np.array(energies)
    probs = np.exp(-energies / temperature)
    probs = probs / np.sum(probs)
    return np.random.choice(len(energies), p=probs)


def _find_img_pair(alpha_t, L, temperature=1):
    """Find best pair of images to combine to aspect ratio alpha_t."""
    p = 0
    q = len(L) - 1
    energies = []
    pairs = []
    while p < q:
        alpha_sum = L[p].alpha + L[q].alpha
        energies.append(abs(alpha_sum - alpha_t))
        pairs.append((p, q))
        if alpha_sum >= alpha_t:
            q = q - 1
        elif alpha_sum < alpha_t:
            p = p + 1
    i, j = pairs[_sample_energies(energies, temperature)]
    return (i, j)


def _generate_tree(L, node, temperature):
    """Recursively generate layout tree by assigning rectangles to nodes."""
    if node.N == 1:
        energies = np.array([abs(l.alpha - node.alpha_t) for l in L])
        best_fit = L[_sample_energies(energies, temperature)]
        node.rect = best_fit.rect
        L.remove(best_fit)
        return
    if node.N == 2:
        i, j = _find_img_pair(node.alpha_t, L, temperature)
        node.left = L[i]
        node.right = L[j]
        node.left.parent = node
        node.right.parent = node
        del L[j]
        del L[i]
        return
    node.split = np.random.choice(["V", "H"])
    if node.split == "V":
        node.left = Node(parent=node, N=math.floor(node.N / 2), alpha_t=node.alpha_t / 2)
        node.right = Node(parent=node, N=math.ceil(node.N / 2), alpha_t=node.alpha_t / 2)
    else:
        node.left = Node(parent=node, N=math.floor(node.N / 2), alpha_t=node.alpha_t * 2)
        node.right = Node(parent=node, N=math.ceil(node.N / 2), alpha_t=node.alpha_t * 2)
    _generate_tree(L, node.left, temperature)
    _generate_tree(L, node.right, temperature)


def _adjust_tree(node, th):
    """Adjust tree splits to better match target aspect ratios."""
    if node.rect is not None:
        return
    if node.alpha > node.alpha_t * th:
        node.split = "H"
    elif node.alpha < node.alpha_t / th:
        node.split = "V"
    if node.split == "V":
        node.left.alpha_t = node.alpha_t / 2
        node.right.alpha_t = node.alpha_t / 2
    else:
        node.left.alpha_t = node.alpha_t * 2
        node.right.alpha_t = node.alpha_t * 2
    _adjust_tree(node.left, th)
    _adjust_tree(node.right, th)


def _generate_and_adjust_tree(rectangles, ratio, th, temperature):
    """Generate and iteratively adjust layout tree."""
    L = [Node(N=1, rect=rect) for rect in rectangles]
    L.sort(key=lambda node: node.alpha)
    root = Node(N=len(L), alpha_t=ratio)
    _generate_tree(L, root, temperature)
    for _ in range(10):
        _adjust_tree(root, th)
    return root


def _generate_best_tree(rectangles, target_ratio, threshold=1e-4, temperature=1):
    """Generate layout tree with best aspect ratio matching."""
    best_tree = None
    best_error = -1
    for th in np.arange(10) / 50 + 0.55:
        for _ in range(500):
            root = _generate_and_adjust_tree(rectangles, target_ratio, th, temperature)
            if abs(root.alpha - target_ratio) < best_error or best_error == -1:
                best_error = abs(root.alpha - target_ratio)
                best_tree = root
            if best_error < threshold:
                break
    return best_tree


class CollageGeneratorAlgorithm(LayoutAlgorithm):
    """Layout algorithm using collage-generator (Wu et al. 2016).
    
    This algorithm operates on abstract items and pages, taking no knowledge of
    file paths or MCF coordinates. The wrapper translates photos to items
    (with dimensions from image metadata) and back.
    """
    
    def __init__(self, temperature=1.0, threshold=1e-4):
        """
        Initialize collage-generator algorithm.
        
        Args:
            temperature: Boltzmann temperature for energy sampling (higher = more random).
            threshold: Target aspect ratio error threshold.
        """
        self.temperature = temperature
        self.threshold = threshold
    
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles,
        **kwargs
    ):
        """Generate layout for rectangles on a page.
        
        Args:
            page_width: Page width in page coordinates.
            page_height: Page height in page coordinates.
            rectangles: List of LayoutRectangle objects with width, height, preferred_size.
            **kwargs: Additional parameters (unused for collage-generator).
        
        Returns:
            Tuple (success: bool, rects: list, error_msg: str).
        """
        try:
            if not rectangles:
                return False, [], "No rectangles to layout"
            
            # Compute target aspect ratio for the page
            target_ratio = page_width / page_height if page_height > 0 else 1.0
            
            # Generate collage tree directly from rectangles
            tree = _generate_best_tree(
                rectangles, target_ratio,
                threshold=self.threshold,
                temperature=self.temperature
            )
            
            # Extract layout from tree and update rectangles in-place
            self._extract_layout(tree, page_width, page_height, rectangles)
            
            return True, rectangles, ""
        
        except Exception as e:
            return False, [], f"Layout generation error: {e}"
    
    def _extract_layout(self, tree_node, page_width, page_height, rectangles):
        """Extract layout from tree and update rectangles in-place with page coordinates."""
        rect_idx = [0]
        
        def traverse(node, x, y, height):
            if node.rect is not None:
                # Leaf node - assign position and size to the rectangle
                new_width = node.alpha * height
                if rect_idx[0] < len(rectangles):
                    rect = rectangles[rect_idx[0]]
                    rect.x = x
                    rect.y = y
                    rect.width = new_width
                    rect.height = height
                    # Collage-generator achieves the preferred size (no scaling)
                    rect.actual_size = rect.preferred_size
                rect_idx[0] += 1
                return
            
            # Internal node - recursively traverse children
            alpha = node.alpha
            l_alpha = node.left.alpha
            r_alpha = node.right.alpha
            width = alpha * height
            
            if node.split == "V":
                # Vertical split: left and right side by side
                traverse(node.left, x, y, height)
                traverse(node.right, x + width * l_alpha / alpha, y, height)
            else:
                # Horizontal split: left on top, right on bottom
                left_height = height * alpha / l_alpha
                traverse(node.left, x, y, left_height)
                traverse(node.right, x, y + left_height, height * alpha / r_alpha)
        
        traverse(tree_node, 0, 0, page_height)
