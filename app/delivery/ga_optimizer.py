"""
GA + 2-opt 路径优化模块（对应 daima.py 的步骤4）

职责：
- 使用遗传算法（Genetic Algorithm）求解 TSP（旅行商问题）
- 结合 2-opt 局部搜索进一步优化路径
- 返回最优路线和距离

核心算法说明：
- 遗传算法：模拟自然进化，通过选择、交叉、变异来搜索最优解
- 2-opt：对路径中的两条边进行反转，尝试找到更短的路径
- 两者结合：GA 负责全局搜索，2-opt 负责局部精细优化

这个类从 daima.py 的 GeneticAlgorithmTSPWith2Opt 类直接迁移而来，
去掉了 matplotlib 绘图部分，增加了进度回调支持。
"""

import random
import numpy as np


class GeneticAlgorithmTSPWith2Opt:
    """
    结合 2-opt 局部搜索的遗传算法

    用法:
        ga = GeneticAlgorithmTSPWith2Opt(distance_matrix)
        best_route, best_distance = ga.solve()
    """

    def __init__(self, distance_matrix, population_size=200, generations=500,
                 mutation_rate=0.2, crossover_rate=0.8, use_2opt=True,
                 apply_2opt_interval=10):
        """
        初始化 GA 求解器

        参数:
            distance_matrix: numpy 二维数组，distance_matrix[i][j] 表示
                            位置 i 到位置 j 的距离（米）
            population_size: 种群大小（每代有多少个候选解）
            generations: 最大进化代数
            mutation_rate: 变异概率（0~1），控制探索新解的力度
            crossover_rate: 交叉概率（0~1），控制父代基因组合的概率
            use_2opt: 是否启用 2-opt 局部搜索
            apply_2opt_interval: 每隔多少代应用一次 2-opt
        """
        self.distance_matrix = distance_matrix
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.use_2opt = use_2opt
        self.apply_2opt_interval = apply_2opt_interval
        self.n_cities = len(distance_matrix)

        # 记录优化过程数据（用于前端绘制收敛曲线）
        self.best_distances = []
        self.best_route = None
        self.best_distance = float('inf')

    def calculate_distance(self, route):
        """
        计算一条路线的总距离

        路线是一个闭环：route[0] → route[1] → ... → route[-1] → route[0]

        参数:
            route: list[int] — 位置索引的访问顺序

        返回:
            float: 总距离（米），如果路线无效返回 inf
        """
        if None in route:
            return float('inf')

        total = 0
        for i in range(len(route)):
            from_city = route[i]
            to_city = route[(i + 1) % len(route)]

            if (from_city >= len(self.distance_matrix) or
                    to_city >= len(self.distance_matrix)):
                return float('inf')

            total += self.distance_matrix[from_city][to_city]

        return total

    def two_opt(self, route):
        """
        2-opt 局部搜索

        原理：选择路径中的两个位置 i, j，将 i 到 j 之间的路段反转，
        如果反转后总距离更短，就接受这个改变。
        重复直到没有改进为止。

        这是对 GA 全局搜索的补充：GA 找到大致方向，2-opt 做精细调整。
        """
        best_route = route[:]
        best_distance = self.calculate_distance(best_route)
        improved = True
        iterations = 0

        while improved and iterations < 100:
            improved = False
            iterations += 1

            for i in range(1, len(route) - 1):
                for j in range(i + 2, len(route)):
                    if j == len(route) - 1:
                        continue

                    new_route = route[:]
                    new_route[i:j] = reversed(new_route[i:j])
                    new_distance = self.calculate_distance(new_route)

                    if new_distance < best_distance:
                        best_route = new_route
                        best_distance = new_distance
                        improved = True
                        break
                if improved:
                    break
            route = best_route

        return best_route

    def initialize_population(self):
        """
        初始化种群

        每个个体是一条路线：[0, ...随机排列的其他城市...]
        0 代表食堂（起点），固定在最前面
        """
        population = []
        cities = list(range(1, self.n_cities))  # 除了食堂(0)之外的所有城市

        for _ in range(self.population_size):
            route = [0] + random.sample(cities, len(cities))
            population.append(route)

        return population

    def selection(self, population, fitness):
        """轮盘赌选择：适应度越高（距离越短），被选中的概率越大"""
        total_fitness = sum(fitness)
        if total_fitness == 0:
            probabilities = [1 / len(population)] * len(population)
        else:
            probabilities = [f / total_fitness for f in fitness]

        selected_indices = np.random.choice(
            len(population), size=2, p=probabilities, replace=False
        )
        return population[selected_indices[0]], population[selected_indices[1]]

    def crossover(self, parent1, parent2):
        """
        顺序交叉（OX - Order Crossover）

        从 parent1 中截取一段，填入 child1，
        剩余位置按 parent2 的顺序补齐（跳过已有的城市）
        """
        if random.random() > self.crossover_rate:
            return parent1[:], parent2[:]

        size = len(parent1)
        if size <= 2:
            return parent1[:], parent2[:]

        start, end = sorted(random.sample(range(1, size), 2))

        child1 = [-1] * size
        child2 = [-1] * size
        child1[0] = 0
        child2[0] = 0
        child1[start:end] = parent1[start:end]
        child2[start:end] = parent2[start:end]

        def fill_child(child, other_parent, start, end):
            child_set = set(child) - {-1}
            to_fill = [c for c in other_parent[end:] + other_parent[1:end]
                       if c not in child_set]
            fill_positions = [i for i in range(1, start) if child[i] == -1] + \
                             [i for i in range(end, len(child)) if child[i] == -1]
            for i, pos in enumerate(fill_positions):
                if i < len(to_fill):
                    child[pos] = to_fill[i]

        fill_child(child1, parent2, start, end)
        fill_child(child2, parent1, start, end)

        # 修复可能遗漏的位置
        def fix_child(child, parent):
            unfilled = [i for i, v in enumerate(child) if v == -1]
            if unfilled:
                child_set = set(child) - {-1}
                missing = [i for i in range(len(parent)) if i not in child_set]
                for i, pos in enumerate(unfilled):
                    if i < len(missing):
                        child[pos] = missing[i]
            return child

        child1 = fix_child(child1, parent1)
        child2 = fix_child(child2, parent2)
        return child1, child2

    def mutate(self, route):
        """
        变异操作（三种方式随机选择）
        - swap: 交换两个城市的位置
        - insert: 把一个城市拔出来插到另一个位置
        - reverse: 反转一段子路径
        """
        if random.random() < self.mutation_rate:
            mutation_type = random.choice(['swap', 'insert', 'reverse'])

            if mutation_type == 'swap' and len(route) > 2:
                i, j = random.sample(range(1, len(route)), 2)
                route[i], route[j] = route[j], route[i]
            elif mutation_type == 'insert' and len(route) > 3:
                i = random.randint(1, len(route) - 1)
                j = random.randint(1, len(route) - 1)
                if i != j:
                    city = route.pop(i)
                    route.insert(j, city)
            elif mutation_type == 'reverse' and len(route) > 3:
                i, j = sorted(random.sample(range(1, len(route)), 2))
                route[i:j] = reversed(route[i:j])

        return route

    def solve(self):
        """
        求解 TSP 问题（主函数）

        返回:
            tuple: (最优路线, 最优距离)
                - 最优路线: list[int] — 位置索引的访问顺序
                - 最优距离: float — 总距离（米）
        """
        population = self.initialize_population()
        no_improvement_count = 0

        for generation in range(self.generations):
            # 计算每个个体的适应度（距离越短，适应度越高）
            distances = [self.calculate_distance(r) for r in population]
            fitness = [1 / d if 0 < d < float('inf') else 0 for d in distances]

            # 更新全局最优
            valid = [d for d in distances if d != float('inf')]
            if valid:
                min_d = min(valid)
                if min_d < self.best_distance:
                    self.best_distance = min_d
                    self.best_route = population[distances.index(min_d)][:]
                    no_improvement_count = 0
                else:
                    no_improvement_count += 1

            # 定期应用 2-opt
            if (self.use_2opt and
                    (generation + 1) % self.apply_2opt_interval == 0 and
                    self.best_route is not None):
                self.best_route = self.two_opt(self.best_route)
                new_d = self.calculate_distance(self.best_route)
                if new_d < self.best_distance:
                    self.best_distance = new_d
                    no_improvement_count = 0

            self.best_distances.append(self.best_distance)

            # 生成下一代
            new_population = [self.best_route[:]] if self.best_route else []
            while len(new_population) < self.population_size:
                p1, p2 = self.selection(population, fitness)
                c1, c2 = self.crossover(p1, p2)
                c1 = self.mutate(c1)
                c2 = self.mutate(c2)
                new_population.extend([c1, c2])

            population = new_population[:self.population_size]

            # 提前终止判断
            if no_improvement_count > 100:
                print(f"  GA 在第 {generation + 1} 代收敛，提前终止")
                break

        return self.best_route, self.best_distance