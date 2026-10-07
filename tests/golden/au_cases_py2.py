# Runs under Python 2.7 against the ORIGINAL Clone Digger 1.1.0, to record how its
# anti-unification behaves. The output is the reference the Python 3 port must match.
import sys, json
sys.path.insert(0, '/w/legacy/clonedigger')
from abstract_syntax_tree import AbstractSyntaxTree
import anti_unification as au

def T(name, *children):
    t = AbstractSyntaxTree(name, [])
    for c in children:
        t.addChild(c)
    return t

def show(t):
    if isinstance(t, au.FreeVariable):
        return 'VAR'
    if not t.getChilds():
        return t.getName()
    return '%s(%s)' % (t.getName(), ', '.join(show(c) for c in t.getChilds()))

cases = {
  'rename_and_constant': (T('Assign', T('total'), T('Mult', T('prix'), T('1.2'))),
                          T('Assign', T('remise'), T('Mult', T('prix'), T('0.9')))),
  'same_difference_twice': (T('Add', T('a'), T('a')), T('Add', T('b'), T('b'))),
  'two_differences': (T('Add', T('a'), T('a')), T('Add', T('b'), T('c'))),
  'identical': (T('Call', T('f'), T('x')), T('Call', T('f'), T('x'))),
  'different_shape': (T('Call', T('f'), T('x')), T('Call', T('f'), T('x'), T('y'))),
  'subtree_differs': (T('Return', T('Mult', T('a'), T('b'))), T('Return', T('Add', T('a'), T('b')))),
}
out = {}
for name, (t1, t2) in sorted(cases.items()):
    u = au.Unifier(t1, t2)
    s1, s2 = u.getSubstitutions()
    out[name] = {
        'pattern': show(u.getUnifier()),
        'variables': len(s1.getMap()),
        'substitution_sizes': [s1.getSize(), s2.getSize()],
        'distance': u.getSize(),
        'substitutions': [sorted(show(v) for v in s1.getMap().values()),
                          sorted(show(v) for v in s2.getMap().values())],
    }
print(json.dumps(out, indent=1, sort_keys=True))
