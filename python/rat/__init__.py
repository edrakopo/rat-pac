import os, types, re
RATROOT = os.environ["RATROOT"]

import sys
# Hide command line options from $!$#! ROOT
_argv = sys.argv
sys.argv = sys.argv[:1]

# Load this shared library before ROOT
import ctypes
try:
    ctypes.cdll.LoadLibrary(os.path.join(RATROOT, 'lib', 'libSilenceRooFitBanner.so'))
except OSError:
    ctypes.cdll.LoadLibrary(os.path.join(RATROOT, 'lib', 'libSilenceRooFitBanner.dylib'))

import ROOT
from ROOT import gROOT, TH1F
# Detect if we already loaded the dictionary, for example inside RAT already
if ROOT.TClassTable.GetID("RAT::DS::Root") == -1:
    gROOT.ProcessLine(".x "+os.path.join(RATROOT, "src/rootinit.C"))
from ROOT import RAT

# Unhide command line options from $!$#! ROOT
sys.argv = _argv
del _argv


import rat.parser

def dsreader(filename):
    """Read the RAT::DS data structures from a ROOT file

    Returns an iterator over the RAT::DS objects stored in the file
    called [filename].  Assumes file was generated by rat and has
    the TTree named "T" and the event branch named "ds"."""
    r = RAT.DSReader(filename)
    ds = r.NextEvent()
    while ds:
        yield RAT.DS.Root(ds)
        ds = r.NextEvent()

def ratiter(element, selector=""):
    """Creates iterator over arbitrary member of data structure.

    The selector describes the element to loop over.  It is a
    dotted hierarchy of data structure names.  For example:
      mc.particle.px
      ev.pmt
      ev.efit.ke

    The selector is applied to element.  If element is a string, then
    it is assumed to be a filename, and that file is opened, and the
    selector applied to each RAT.DS event in the file.  You may also
    pass an object in the data structure (like a RAT.MC), in which
    case the selector should be relative to that.  The previous example
    would become:
      particle.px
    in such a scenario.

    The empty selector "" will generate an iterator that just contains
    one item, the element, if it is not a C++ vector.  If it is a vector
    then iterator will return each item in the vector sequentially."""
    evaluation_tree = rat.parser.create_evaluation_tree(*selector.split(':'))

    if isinstance(element, types.StringTypes):
        # If element is a string, assume it is a filename and
        # start iterating through events
        for ds in dsreader(element):
            for row in evaluation_tree.eval(ds):
                if len(row) == 1:
                    yield row[0]
                else:
                    yield row
    else:
        for row in evaluation_tree.eval(element):
            if len(row) == 1:
                yield row[0]
            else:
                yield row

# Only create these function if numpy exists
def get_array(args):
    filename, selector, dtype = args
    return ratarray(filename, selector, dtype=dtype)

try:
    import numpy as np
    def ratarray(element, selector="", dtype=float):
        """Returns a 1 or 2D numpy array of the values that would be
        returned by ratiter(element, selector)."""
        if isinstance(element, (list, tuple)):
            return parallel_ratarray(element, selector, dtype)
        else:
            return np.array(list(ratiter(element, selector)), dtype=dtype)

    # This function requires the multiprocessing module (Python 2.6 and later)
    import multiprocessing

    def parallel_ratarray(filenames, selector, dtype=float):
        '''Helper function to ratiter() that is called when a list of 
        filenames is passed to ratiter().

        Spawns multiple processes to loop over the files in parallel.
        Warm up your SSDs!'''
        RATITER_POOL = multiprocessing.Pool()

        results = RATITER_POOL.map(get_array, [(f,selector,dtype) 
                                               for f in filenames])
        return np.concatenate(results)

except ImportError:
    pass


def lookup(name):
    """Looks up an object in gDirectory"""
    return ROOT.gDirectory.Get(name)

def browse():
    """Create a new TBrowser and return it"""
    return ROOT.TBrowser()

def extract_db(root_file):
    """Extract the database information from the provided TFile object.
    
       Returns a triple nested dictionary: db[tablename][indexname][fieldname]
       (remember that no index is the same as the empty string '')
    """
    db = root_file.Get('db')

    # Convert the flat list of field values into nested dictionaries
    # grouped for generation of .ratdb file: table(index(field))
    tables = {}
    ratdb_pattern = re.compile(r'(?P<table>.*)\[(?P<index>.*)\]\.(?P<field>.*)')
    for key in db:
        match = ratdb_pattern.match(str(key))
        if match:
            tablename = match.group('table')
            indexname = match.group('index')
            fieldname = match.group('field')

            # Find this table set
            if not tables.has_key(tablename):
                tables[tablename] = {}

            # Find this index in the table set
            if not tables[tablename].has_key(indexname):
                tables[tablename][indexname] = {}

            # Set the field attribute
            tables[tablename][indexname][fieldname] = str(db.FindObject(key).Value())
    return tables
