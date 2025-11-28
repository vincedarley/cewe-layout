"""
Genetic algorithm for photo layout optimization.

This module implements a genetic algorithm approach to optimize photo placement
on a page, inspired by evolutionary optimization techniques for layout problems.

The algorithm represents layouts as chromosomes (permutations + placement parameters),
evolves them through selection, crossover, and mutation, and evaluates fitness based
on space utilization and aesthetic criteria.

Attribution:
    Inspired by genetic algorithm approaches to photo layout optimization,
    including work on adaptive grid layouts and multi-objective optimization.
"""

import random
import math
from typing import List, Tuple, Optional

from .base import LayoutAlgorithm


class Chromosome:
    """Represents a layout solution as a chromosome for genetic algorithm."""
    
    def __init__(self, rectangles, page_width, page_height):
        """
        Initialize chromosome with random layout.
        
        Args:
            rectangles: List of LayoutRectangle objects to place.
            page_width: Width of the page.
            page_height: Height of the page.
        """
        self.num_rects = len(rectangles)
        self.page_width = page_width
        self.page_height = page_height
        
        # Permutation: order in which to place rectangles
        self.permutation = list(range(self.num_rects))
        random.shuffle(self.permutation)
        
        # Grid parameters: rows and columns
        self.rows = random.randint(1, max(1, int(math.sqrt(self.num_rects))))
        self.cols = math.ceil(self.num_rects / self.rows)
        
        self.fitness = None
        self.layout = None
    
    def clone(self):
        """Create a deep copy of this chromosome."""
        new_chrom = Chromosome.__new__(Chromosome)
        new_chrom.num_rects = self.num_rects
        new_chrom.page_width = self.page_width
        new_chrom.page_height = self.page_height
        new_chrom.permutation = self.permutation.copy()
        new_chrom.rows = self.rows
        new_chrom.cols = self.cols
        new_chrom.fitness = self.fitness
        new_chrom.layout = None
        return new_chrom


def _evaluate_fitness(chromosome, rectangles, page_width, page_height):
    """
    Evaluate fitness of a chromosome's layout.
    
    Fitness considers:
    - Space utilization (how much of page is covered)
    - Uniformity (how evenly rectangles are sized)
    - Aspect ratio preservation (minimal distortion)
    
    Args:
        chromosome: Chromosome to evaluate.
        rectangles: List of LayoutRectangle objects.
        page_width: Page width.
        page_height: Page height.
    
    Returns:
        Fitness score (higher is better).
    """
    # Generate layout from chromosome
    layout = _chromosome_to_layout(chromosome, rectangles, page_width, page_height)
    chromosome.layout = layout
    
    # Calculate fitness components
    
    # 1. Coverage: fraction of page area covered by photos
    total_photo_area = sum(r.width * r.height for r in layout)
    page_area = page_width * page_height
    coverage = total_photo_area / page_area if page_area > 0 else 0
    
    # 2. Uniformity: inverse of size variance (prefer similar-sized rectangles)
    if len(layout) > 1:
        areas = [r.width * r.height for r in layout]
        mean_area = sum(areas) / len(areas)
        variance = sum((a - mean_area) ** 2 for a in areas) / len(areas)
        uniformity = 1.0 / (1.0 + variance / (mean_area ** 2)) if mean_area > 0 else 0
    else:
        uniformity = 1.0
    
    # 3. Aspect ratio preservation: how well original aspect ratios are preserved
    aspect_preservation = 0
    for orig, placed in zip(rectangles, layout):
        orig_aspect = orig.width / orig.height if orig.height > 0 else 1.0
        placed_aspect = placed.width / placed.height if placed.height > 0 else 1.0
        # Penalize aspect ratio distortion
        distortion = abs(orig_aspect - placed_aspect) / orig_aspect if orig_aspect > 0 else 0
        aspect_preservation += 1.0 / (1.0 + distortion)
    aspect_preservation /= len(rectangles) if rectangles else 1
    
    # Combined fitness (weighted sum)
    fitness = (
        0.5 * coverage +
        0.25 * uniformity +
        0.25 * aspect_preservation
    )
    
    return fitness


def _chromosome_to_layout(chromosome, rectangles, page_width, page_height):
    """
    Convert chromosome to actual layout by placing rectangles in grid.
    
    Args:
        chromosome: Chromosome defining the layout.
        rectangles: Original rectangles (in chromosome permutation order).
        page_width: Page width.
        page_height: Page height.
    
    Returns:
        List of LayoutRectangle objects with updated positions and sizes.
    """
    # Reorder rectangles according to permutation
    ordered_rects = [rectangles[i].clone() for i in chromosome.permutation]
    
    # Calculate grid cell dimensions
    cell_width = page_width / chromosome.cols
    cell_height = page_height / chromosome.rows
    
    # Place rectangles in grid cells
    for idx, rect in enumerate(ordered_rects):
        row = idx // chromosome.cols
        col = idx % chromosome.cols
        
        # Cell boundaries
        x_start = col * cell_width
        y_start = row * cell_height
        
        # Original aspect ratio
        orig_aspect = rect.width / rect.height if rect.height > 0 else 1.0
        
        # Fit rectangle into cell while preserving aspect ratio
        # Try to fill cell width
        new_width = cell_width
        new_height = new_width / orig_aspect
        
        # If height exceeds cell, fit to height instead
        if new_height > cell_height:
            new_height = cell_height
            new_width = new_height * orig_aspect
        
        # Center in cell
        x_offset = (cell_width - new_width) / 2
        y_offset = (cell_height - new_height) / 2
        
        rect.x = x_start + x_offset
        rect.y = y_start + y_offset
        rect.width = new_width
        rect.height = new_height
        rect.actual_size = rect.preferred_size
    
    return ordered_rects


def _selection(population, k=3):
    """
    Tournament selection: choose best from k random candidates.
    
    Args:
        population: List of (chromosome, fitness) tuples.
        k: Tournament size.
    
    Returns:
        Selected chromosome.
    """
    tournament = random.sample(population, min(k, len(population)))
    return max(tournament, key=lambda x: x[1])[0]


def _crossover(parent1, parent2):
    """
    Create offspring by combining two parent chromosomes.
    
    Uses order crossover (OX) for permutation and averaging for grid parameters.
    
    Args:
        parent1: First parent chromosome.
        parent2: Second parent chromosome.
    
    Returns:
        Two offspring chromosomes.
    """
    child1 = parent1.clone()
    child2 = parent2.clone()
    
    # Crossover permutation using order crossover (OX)
    size = len(parent1.permutation)
    if size > 1:
        # Select crossover segment
        cx_point1 = random.randint(0, size - 1)
        cx_point2 = random.randint(cx_point1, size - 1)
        
        # Order crossover for child1
        child1_perm = [-1] * size
        child1_perm[cx_point1:cx_point2+1] = parent1.permutation[cx_point1:cx_point2+1]
        
        # Fill remaining positions from parent2
        pos = cx_point2 + 1
        for val in parent2.permutation[cx_point2+1:] + parent2.permutation[:cx_point2+1]:
            if val not in child1_perm:
                if pos >= size:
                    pos = 0
                child1_perm[pos] = val
                pos += 1
        
        child1.permutation = child1_perm
        
        # Similar for child2
        child2_perm = [-1] * size
        child2_perm[cx_point1:cx_point2+1] = parent2.permutation[cx_point1:cx_point2+1]
        
        pos = cx_point2 + 1
        for val in parent1.permutation[cx_point2+1:] + parent1.permutation[:cx_point2+1]:
            if val not in child2_perm:
                if pos >= size:
                    pos = 0
                child2_perm[pos] = val
                pos += 1
        
        child2.permutation = child2_perm
    
    # Crossover grid parameters (averaging with random choice)
    if random.random() < 0.5:
        child1.rows = parent1.rows
        child2.rows = parent2.rows
    else:
        child1.rows = parent2.rows
        child2.rows = parent1.rows
    
    child1.cols = math.ceil(child1.num_rects / child1.rows)
    child2.cols = math.ceil(child2.num_rects / child2.rows)
    
    return child1, child2


def _mutate(chromosome, mutation_rate=0.1):
    """
    Apply mutation to chromosome.
    
    Args:
        chromosome: Chromosome to mutate.
        mutation_rate: Probability of mutation.
    """
    # Mutate permutation (swap two random positions)
    if random.random() < mutation_rate and len(chromosome.permutation) > 1:
        i, j = random.sample(range(len(chromosome.permutation)), 2)
        chromosome.permutation[i], chromosome.permutation[j] = \
            chromosome.permutation[j], chromosome.permutation[i]
    
    # Mutate grid parameters
    if random.random() < mutation_rate:
        max_rows = max(1, chromosome.num_rects)
        chromosome.rows = random.randint(1, max_rows)
        chromosome.cols = math.ceil(chromosome.num_rects / chromosome.rows)


class GeneticPhotoLayoutAlgorithm(LayoutAlgorithm):
    """
    Layout algorithm using genetic optimization.
    
    Evolves layout solutions through selection, crossover, and mutation
    to optimize space utilization and aesthetic quality.
    """
    
    def __init__(self, population_size=50, generations=100, mutation_rate=0.1,
                 crossover_rate=0.8, tournament_size=3):
        """
        Initialize genetic algorithm parameters.
        
        Args:
            population_size: Number of candidate solutions in population.
            generations: Number of evolution iterations.
            mutation_rate: Probability of mutation per chromosome.
            crossover_rate: Probability of crossover between parents.
            tournament_size: Number of candidates in tournament selection.
        """
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.tournament_size = tournament_size
    
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles,
        **kwargs
    ):
        """
        Generate layout using genetic algorithm.
        
        Args:
            page_width: Page width in page coordinates.
            page_height: Page height in page coordinates.
            rectangles: List of LayoutRectangle objects.
            **kwargs: Additional parameters (unused).
        
        Returns:
            Tuple (success: bool, rects: list, error_msg: str).
        """
        try:
            if not rectangles:
                return False, [], "No rectangles to layout"
            
            # Initialize population
            population = []
            for _ in range(self.population_size):
                chrom = Chromosome(rectangles, page_width, page_height)
                fitness = _evaluate_fitness(chrom, rectangles, page_width, page_height)
                chrom.fitness = fitness
                population.append((chrom, fitness))
            
            # Evolution loop
            for generation in range(self.generations):
                new_population = []
                
                # Elitism: keep best solution
                best = max(population, key=lambda x: x[1])
                new_population.append(best)
                
                # Generate offspring
                while len(new_population) < self.population_size:
                    # Selection
                    parent1 = _selection(population, self.tournament_size)
                    parent2 = _selection(population, self.tournament_size)
                    
                    # Crossover
                    if random.random() < self.crossover_rate:
                        child1, child2 = _crossover(parent1, parent2)
                    else:
                        child1 = parent1.clone()
                        child2 = parent2.clone()
                    
                    # Mutation
                    _mutate(child1, self.mutation_rate)
                    _mutate(child2, self.mutation_rate)
                    
                    # Evaluate
                    fitness1 = _evaluate_fitness(child1, rectangles, page_width, page_height)
                    fitness2 = _evaluate_fitness(child2, rectangles, page_width, page_height)
                    child1.fitness = fitness1
                    child2.fitness = fitness2
                    
                    new_population.append((child1, fitness1))
                    if len(new_population) < self.population_size:
                        new_population.append((child2, fitness2))
                
                population = new_population
            
            # Extract best solution
            best_chromosome, best_fitness = max(population, key=lambda x: x[1])
            best_layout = best_chromosome.layout
            
            # Update input rectangles in-place with best layout
            # Map back from permutation order to original order
            inverse_perm = [0] * len(best_chromosome.permutation)
            for i, p in enumerate(best_chromosome.permutation):
                inverse_perm[p] = i
            
            for orig_idx, rect in enumerate(rectangles):
                layout_idx = inverse_perm[orig_idx]
                placed = best_layout[layout_idx]
                rect.x = placed.x
                rect.y = placed.y
                rect.width = placed.width
                rect.height = placed.height
                rect.actual_size = placed.actual_size
            
            return True, rectangles, ""
        
        except Exception as e:
            return False, [], f"Genetic layout error: {e}"
