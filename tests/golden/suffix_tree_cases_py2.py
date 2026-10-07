# Runs under Python 2.7 against the ORIGINAL Clone Digger 1.1.0 suffix tree, to record
# which pairs of repeated substrings it reports. Each element of a string is one
# character, its own code; every element weighs 1, and a candidate's size is its length.
import sys, json
sys.path.insert(0, '/w/legacy/clonedigger')
from suffix_tree import SuffixTree

cases = {
    'peter': (['abcPeter', 'Pet1erbca', 'Peter', 'aPet0--'], 3),
    'a_aa': (['a', 'aa'], 0),
    'repeat_inside': (['xabcyabcz'], 2),
    'no_repeat': (['abc', 'xyz'], 1),
    'three_copies': (['qabcr', 'sabct', 'uabcv'], 3),
    'equal_strings': (['xabc', 'xabc', 'yabc'], 2),
    'zero_threshold': (['ab', 'cd', 'cb'], 0),
}
out = {}
for name, (words, threshold) in sorted(cases.items()):
    tree = SuffixTree(lambda e: e)
    for w in words:
        tree.add(list(w))
    pairs = tree.getBestMaxSubstrings(threshold, lambda code: 1, len)
    out[name] = {'words': words, 'threshold': threshold,
                 'pairs': sorted(sorted([''.join(a), ''.join(b)]) for a, b in pairs)}
print(json.dumps(out, indent=1, sort_keys=True))
