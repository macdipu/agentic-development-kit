from collections import defaultdict, deque

class DependencyGraph:
    def __init__(self):
        self.edges = defaultdict(set)
    def add(self, module, dependency):
        self.edges[module].add(dependency)
    def closure(self, modules):
        seen, q = set(modules), deque(modules)
        while q:
            m = q.popleft()
            for dep in self.edges.get(m, ()): 
                if dep not in seen:
                    seen.add(dep); q.append(dep)
        return sorted(seen)
