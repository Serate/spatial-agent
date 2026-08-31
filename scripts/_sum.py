import io, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root
def summarize(mods):
    for mod in mods:
        suite = unittest.defaultTestLoader.loadTestsFromName(mod)
        r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        for t, tb in r.failures:
            print('FAIL', t.id())
            for line in tb.splitlines()[::-1]:
                ls = line.strip()
                if any(x in ls for x in ('AssertionError','Error','not found','400','List','bound','!= ','set','Items','KeyError','not in')):
                    print('  ', ls[:150]); break
        for t, tb in r.errors:
            print('ERROR', t.id())
            for line in tb.splitlines():
                if 'Error' in line.strip():
                    print('  ', line.strip()[:150]); break
summarize(sys.argv[1:])
