import timeit

def benchmark_list_membership():
    return 'Farm' in ['Management', 'Farm']

def benchmark_set_membership():
    return 'Farm' in {'Management', 'Farm'}

def benchmark_frozenset_membership():
    # Simulate a predefined module-level constant
    ROLES = frozenset(['Management', 'Farm'])
    def test_in_frozenset():
        return 'Farm' in ROLES
    return test_in_frozenset()

if __name__ == '__main__':
    list_time = timeit.timeit("benchmark_list_membership()", setup="from __main__ import benchmark_list_membership", number=10000000)
    set_time = timeit.timeit("benchmark_set_membership()", setup="from __main__ import benchmark_set_membership", number=10000000)

    # Also benchmark the direct constant check
    ROLES = frozenset(['Management', 'Farm'])
    const_time = timeit.timeit("'Farm' in ROLES", globals=globals(), number=10000000)

    print(f"List Membership Time (10M ops): {list_time:.4f}s")
    print(f"Set Membership Time (10M ops): {set_time:.4f}s")
    print(f"Frozenset Constant Membership Time (10M ops): {const_time:.4f}s")
