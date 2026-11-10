import json
import os

BASE = os.path.dirname(__file__)
docs = json.load(open(os.path.join(BASE, "corpus", "lumerical_v241", "docs.json"), encoding="utf-8"))
keys = {k.lower(): k for k in docs}

cand = """find findpeaks max min abs sum integrate interp interp1 linspace length transpose real imag conj
matrixmult matrix getresult getdata getsweepresult getnamed getnamednumber ? format num2str sort median
pinch squeeze meshgrid unwrap diff cumsum mean std angle sqrt log exp floor ceil round mod
setnamed setanalysis addpower addprofile addindex adddftmonitor exportcsv exportfigure
switchtolayout run load save sethandle getnumber getstruct
""".split()

print("%-18s %-8s %s" % ("command", "in v241", "link"))
for c in cand:
    k = keys.get(c)
    print("%-18s %-8s %s" % (c, "YES" if k else "no", (docs.get(k, {}).get("link") if k else "")))
